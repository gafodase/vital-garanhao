"""VITAL GARANHAO — backend Flask + SQLite, com login e cadastro de usuários.

Rodar:
    pip install -r requirements.txt
    python app.py
Abrir: http://localhost:5000
"""
import json
import math
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("VITAL_DB", os.path.join(BASE_DIR, "vital.db"))

DEFAULT_CDI = 14.0
INVESTMENT_TYPES = [
    "CDB", "LCI", "LCA", "Tesouro Selic", "Tesouro IPCA+",
    "Ações", "FIIs", "ETF", "BDR", "Poupança", "Outro",
]
INDEXERS = ["CDI", "PREFIXADO", "IPCA", "FIXO"]
OWNED_TABLES = ("investments", "transactions", "goals")

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,30}$")
MIN_PASSWORD = 8
MAX_PASSWORD = 128
MAX_LOGIN_ATTEMPTS = 5      # tentativas erradas...
LOGIN_WINDOW = 5 * 60       # ...dentro de 5 minutos bloqueiam novas tentativas


def load_secret_key():
    """Chave que assina o cookie de sessão. Fica em secret.key (criada na 1ª execução)."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    path = os.path.join(BASE_DIR, "secret.key")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("HTTPS") == "1",  # use HTTPS=1 ao publicar com https
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=64 * 1024,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    cdi REAL NOT NULL DEFAULT 14,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS investments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    date TEXT NOT NULL,
    indexer TEXT NOT NULL,
    rate REAL NOT NULL,
    maturity TEXT NOT NULL DEFAULT '',
    institution TEXT NOT NULL DEFAULT '',
    quantity REAL,
    unit_price REAL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    description TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT NOT NULL,
    target REAL NOT NULL,
    saved REAL NOT NULL DEFAULT 0,
    auto INTEGER NOT NULL DEFAULT 0
);
"""


# ---------------------------------------------------------------- banco ----
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    # Bancos criados antes do login não tinham user_id: adiciona a coluna sem perder dados.
    for table in OWNED_TABLES:
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
        if "user_id" not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
        db.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table}(user_id)")
    # Metas antigas não tinham o modo automático: adiciona a coluna (desligada) sem perder dados.
    goal_cols = [r[1] for r in db.execute("PRAGMA table_info(goals)")]
    if "auto" not in goal_cols:
        db.execute("ALTER TABLE goals ADD COLUMN auto INTEGER NOT NULL DEFAULT 0")
    # Renda variável guarda quantidade e preço pago; bancos antigos ganham as colunas (vazias).
    inv_cols = [r[1] for r in db.execute("PRAGMA table_info(investments)")]
    for col in ("quantity", "unit_price"):
        if col not in inv_cols:
            db.execute(f"ALTER TABLE investments ADD COLUMN {col} REAL")
    db.commit()
    db.close()


def adopt_legacy_data(db, user_id):
    """Dados antigos (de antes do login) ficam para a primeira conta criada."""
    for table in OWNED_TABLES:
        db.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (user_id,))
    has_settings = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'settings'"
    ).fetchone()
    if has_settings:
        row = db.execute("SELECT value FROM settings WHERE key = 'cdi'").fetchone()
        if row:
            try:
                db.execute("UPDATE users SET cdi = ? WHERE id = ?", (float(row[0]), user_id))
            except (TypeError, ValueError):
                pass


# -------------------------------------------------------------- cálculos ----
def annual_rate(inv, cdi):
    rate = float(inv["rate"])
    if inv["indexer"] == "CDI":
        return (cdi / 100) * (rate / 100)
    if inv["indexer"] == "IPCA":
        return 0.045 + rate / 100  # IPCA aproximado em 4,5% a.a.
    return rate / 100


def gross_value(inv, cdi, as_of):
    days = max(0, (as_of - date.fromisoformat(inv["date"])).days)
    daily = (1 + annual_rate(inv, cdi)) ** (1 / 252) - 1
    business_days = days * 252 / 365
    return float(inv["amount"]) * (1 + daily) ** business_days


def tax_rate(days):
    if days <= 180:
        return 0.225
    if days <= 360:
        return 0.20
    if days <= 720:
        return 0.175
    return 0.15


# Tabela regressiva oficial do IOF: % do rendimento cobrado no resgate, do dia 1 ao dia 29.
IOF_TABLE = [96, 93, 90, 86, 83, 80, 76, 73, 70, 66, 63, 60, 56, 53, 50,
             46, 43, 40, 36, 33, 30, 26, 23, 20, 16, 13, 10, 6, 3]

# Para pessoa física, estes investimentos não pagam IR nem IOF.
TAX_EXEMPT_TYPES = {"LCI", "LCA", "Poupança"}


def iof_rate(days):
    if days >= 30:
        return 0.0
    return IOF_TABLE[max(1, days) - 1] / 100


def is_exempt(inv):
    return inv["type"] in TAX_EXEMPT_TYPES


# ------------------------------------------------------------ cotações ----
# Preço atual de ações, FIIs, ETFs e BDRs vem da brapi.dev (liberada na conta grátis do PythonAnywhere).
# Para mais de 4 ativos a brapi pede um token gratuito: defina BRAPI_TOKEN no ambiente.
QUOTE_TTL = 900         # reaproveita a cotação por 15 minutos
QUOTE_FAIL_TTL = 300    # se a consulta falhar, não tenta de novo por 5 minutos
QUOTE_TIMEOUT = 3       # segundos por consulta, para o site nunca travar
_quotes = {}
TICKER_RE = re.compile(r"^([A-Z0-9]{4}\d{1,2})\b")


def ticker_of(name):
    m = TICKER_RE.match(name or "")
    return m.group(1) if m else None


def fetch_quote(ticker):
    """Consulta o preço atual. Devolve um número ou None."""
    url = "https://brapi.dev/api/quote/" + urllib.parse.quote(ticker)
    token = os.environ.get("BRAPI_TOKEN")
    if token:
        url += "?token=" + urllib.parse.quote(token)
    req = urllib.request.Request(url, headers={"User-Agent": "vital-garanhao"})
    with urllib.request.urlopen(req, timeout=QUOTE_TIMEOUT) as resp:
        data = json.load(resp)
    price = data["results"][0]["regularMarketPrice"]
    price = float(price)
    return price if price > 0 and not math.isnan(price) and not math.isinf(price) else None


def get_quote(ticker):
    now = time.time()
    hit = _quotes.get(ticker)
    if hit and now < hit[1]:
        return hit[0]
    try:
        price = fetch_quote(ticker)
    except Exception:  # sem internet, limite da brapi, ativo inexistente...: segue sem cotação
        price = None
    _quotes[ticker] = (price, now + (QUOTE_TTL if price else QUOTE_FAIL_TTL))
    return price


def quoted_metrics(inv, price, as_of):
    """Renda variável com cotação: valor = quantidade x preço atual (lucro ou prejuízo, sem IR/IOF)."""
    gross = float(inv["quantity"]) * price
    profit = gross - float(inv["amount"])
    return {
        "gross": gross, "profit": profit, "iof": 0.0, "ir": 0.0, "net": gross,
        "days": max(0, (as_of - date.fromisoformat(inv["date"])).days),
        "annual_rate": 0.0, "exempt": False,
    }


def metrics(inv, cdi, as_of):
    gross = gross_value(inv, cdi, as_of)
    profit = max(0.0, gross - float(inv["amount"]))
    days = max(0, (as_of - date.fromisoformat(inv["date"])).days)
    exempt = is_exempt(inv)
    iof = 0.0 if exempt else profit * iof_rate(days)
    ir = 0.0 if exempt else max(0.0, profit - iof) * tax_rate(days)
    net = gross - iof - ir
    return {
        "gross": gross, "profit": profit, "iof": iof, "ir": ir, "net": net,
        "days": days, "annual_rate": annual_rate(inv, cdi), "exempt": exempt,
    }


def add_months(d, months):
    """Último dia do mês, `months` meses depois do mês de `d`."""
    y, m = divmod(d.year * 12 + (d.month - 1) + months + 1, 12)
    first_next = date(y, m + 1, 1)
    return first_next - timedelta(days=1)


def evolution(rows, cdi, today, max_points=48, today_value=None):
    """Série para o gráfico: capital aplicado e valor bruto estimado, mês a mês até hoje."""
    rows = list(rows)
    if not rows:
        return []
    start = min(date.fromisoformat(r["date"]) for r in rows)
    points, cursor = [start], add_months(start, 0)
    while cursor < today:
        if cursor > start:
            points.append(cursor)
        cursor = add_months(cursor, 1)
    if points[-1] != today:
        points.append(today)
    points = points[-max_points:]
    series = []
    for p in points:
        invested = value = 0.0
        for r in rows:
            if date.fromisoformat(r["date"]) <= p:
                invested += float(r["amount"])
                value += today_value[r["id"]] if today_value and p == today and r["id"] in today_value else gross_value(r, cdi, p)
        series.append({"date": p.isoformat(), "invested": round(invested, 2), "value": round(value, 2)})
    return series


def simulate(initial, monthly, rate_pct, years):
    r = (1 + rate_pct / 100) ** (1 / 12) - 1
    months = years * 12
    value = initial
    for _ in range(months):
        value = value * (1 + r) + monthly
    deposits = initial + monthly * months
    return value, deposits, value - deposits


# ------------------------------------------------------------- validação ----
class ValidationError(Exception):
    pass


@app.errorhandler(ValidationError)
def handle_validation(err):
    return jsonify(error=str(err)), 400


@app.errorhandler(413)
def handle_too_large(_err):
    return jsonify(error="Dados grandes demais."), 413


def payload_dict():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Envie os dados em formato JSON.")
    return data


def get_num(data, key, label, minimum=None, exclusive=False, default=None):
    raw = data.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"{label}: informe um número válido.")
    if math.isnan(value) or math.isinf(value):
        raise ValidationError(f"{label}: informe um número válido.")
    if minimum is not None:
        if (exclusive and value <= minimum) or (not exclusive and value < minimum):
            raise ValidationError(f"{label}: valor fora do permitido.")
    return value


def get_text(data, key, label, required=True, max_len=120):
    value = str(data.get(key) or "").strip()
    if required and not value:
        raise ValidationError(f"{label}: campo obrigatório.")
    if len(value) > max_len:
        raise ValidationError(f"{label}: máximo de {max_len} caracteres.")
    return value


def get_date(data, key, label, required=True):
    value = str(data.get(key) or "").strip()
    if not value:
        if required:
            raise ValidationError(f"{label}: informe uma data.")
        return ""
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{label}: data inválida.")
    return value


# ---------------------------------------------------- login e sessão ----
_failed_logins = {}


def _recent_failures(key):
    now = time.time()
    recent = [t for t in _failed_logins.get(key, []) if now - t < LOGIN_WINDOW]
    if recent:
        _failed_logins[key] = recent
    else:
        _failed_logins.pop(key, None)
    return recent


def is_throttled(key):
    return len(_recent_failures(key)) >= MAX_LOGIN_ATTEMPTS


def record_failure(key):
    _failed_logins.setdefault(key, []).append(time.time())


DUMMY_HASH = generate_password_hash("senha-falsa-para-igualar-o-tempo")


def start_session(user_id):
    session.clear()
    session["user_id"] = user_id
    session.permanent = True


def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return get_db().execute(
        "SELECT id, username, cdi FROM users WHERE id = ?", (uid,)
    ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            session.clear()
            return jsonify(error="Faça login para continuar."), 401
        g.user = user
        return view(*args, **kwargs)
    return wrapper


@app.after_request
def secure_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def normalize_username(raw):
    username = str(raw or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValidationError(
            "Usuário: use de 3 a 30 caracteres, só letras, números, ponto, hífen ou underline."
        )
    return username


def validate_password(password):
    if len(password) < MIN_PASSWORD:
        raise ValidationError(f"Senha: use pelo menos {MIN_PASSWORD} caracteres.")
    if len(password) > MAX_PASSWORD:
        raise ValidationError(f"Senha: máximo de {MAX_PASSWORD} caracteres.")


# ---------------------------------------------------------------- rotas ----
@app.get("/")
def index():
    if current_user() is None:
        session.clear()
        return redirect("/login")
    return render_template("index.html")


@app.get("/login")
def login_page():
    if current_user() is not None:
        return redirect("/")
    return render_template("login.html")


@app.post("/api/register")
def api_register():
    d = payload_dict()
    username = normalize_username(d.get("username"))
    password = str(d.get("password") or "")
    confirm = d.get("confirm")
    if confirm is not None and str(confirm) != password:
        raise ValidationError("As senhas não conferem.")
    validate_password(password)

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users(username, password_hash, cdi) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), DEFAULT_CDI),
        )
    except sqlite3.IntegrityError:
        raise ValidationError("Este nome de usuário já está em uso.")
    user_id = cur.lastrowid
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1:
        adopt_legacy_data(db, user_id)
    db.commit()
    start_session(user_id)
    return jsonify(username=username), 201


@app.post("/api/login")
def api_login():
    d = payload_dict()
    username = str(d.get("username") or "").strip().lower()
    password = str(d.get("password") or "")
    if len(password) > MAX_PASSWORD:
        password = ""
    key = f"{request.remote_addr}|{username}"
    if is_throttled(key):
        return jsonify(error="Muitas tentativas erradas. Aguarde alguns minutos e tente de novo."), 429

    user = get_db().execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    # confere a senha mesmo se o usuário não existe, para não revelar quem tem conta
    ok = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password)
    if user is None or not ok:
        record_failure(key)
        return jsonify(error="Usuário ou senha incorretos."), 401

    _failed_logins.pop(key, None)
    start_session(user["id"])
    return jsonify(username=user["username"])


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


def load_b3_assets():
    """Lista fixa de ações, FIIs e ETFs da B3 (arquivo b3_ativos.json): [codigo, nome, tipo]."""
    try:
        with open(os.path.join(BASE_DIR, "b3_ativos.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


B3_ASSETS = load_b3_assets()


@app.get("/api/assets")
@login_required
def api_assets():
    return jsonify(B3_ASSETS)


@app.get("/api/summary")
@login_required
def api_summary():
    db = get_db()
    uid = g.user["id"]
    cdi = float(g.user["cdi"])
    today = date.today()

    investments, groups, live = [], {}, {}
    invested = yielded = 0.0
    inv_rows = db.execute("SELECT * FROM investments WHERE user_id = ? ORDER BY id", (uid,)).fetchall()
    for row in inv_rows:
        m = metrics(row, cdi, today)
        price = None
        if row["type"] in VARIABLE_TYPES and row["quantity"]:
            tk = ticker_of(row["name"])
            price = get_quote(tk) if tk else None
            if price:
                m = quoted_metrics(row, price, today)
                live[row["id"]] = m["gross"]
        invested += row["amount"]
        yielded += m["profit"]
        groups[row["type"]] = groups.get(row["type"], 0.0) + row["amount"]
        investments.append({
            "id": row["id"], "name": row["name"], "type": row["type"],
            "amount": row["amount"], "date": row["date"], "index": row["indexer"],
            "rate": row["rate"], "maturity": row["maturity"], "institution": row["institution"],
            "quantity": row["quantity"], "unit_price": row["unit_price"], "price": price,
            "gross": round(m["gross"], 2), "profit": round(m["profit"], 2),
            "iof": round(m["iof"], 2), "ir": round(m["ir"], 2), "net": round(m["net"], 2),
            "days": m["days"], "annual_rate": round(m["annual_rate"], 6), "exempt": m["exempt"],
        })

    total = sum(groups.values())
    distribution = [
        {"type": k, "amount": round(v, 2), "pct": round(v / total * 100, 1)}
        for k, v in groups.items()
    ] if total else []

    transactions = [
        dict(r) for r in db.execute(
            "SELECT id, description, kind, category, amount, date FROM transactions "
            "WHERE user_id = ? ORDER BY date DESC, id DESC", (uid,))
    ]
    income = sum(t["amount"] for t in transactions if t["kind"] == "income")
    expense = sum(t["amount"] for t in transactions if t["kind"] == "expense")
    cash = income - expense

    # Metas em modo automático somam o total da carteira (capital + rendimento) ao valor guardado fora dela.
    portfolio = invested + yielded
    goals = []
    for row in db.execute("SELECT * FROM goals WHERE user_id = ? ORDER BY id", (uid,)):
        auto = bool(row["auto"])
        current = row["saved"] + (portfolio if auto else 0.0)
        pct = min(100.0, current / row["target"] * 100) if row["target"] else 0.0
        goals.append({
            "id": row["id"], "name": row["name"], "target": row["target"], "saved": row["saved"],
            "auto": auto, "portfolio": round(portfolio, 2), "current": round(current, 2),
            "pct": round(pct, 1), "remaining": round(max(0.0, row["target"] - current), 2),
        })

    return jsonify(
        username=g.user["username"],
        cdi=cdi,
        totals={
            "invested": round(invested, 2), "yield": round(yielded, 2),
            "cash": round(cash, 2), "wealth": round(invested + yielded + cash, 2),
        },
        investments=investments, distribution=distribution,
        evolution=evolution(inv_rows, cdi, today, today_value=live),
        transactions=transactions, income=round(income, 2), expense=round(expense, 2),
        goals=goals,
    )


def as_bool(value):
    return value is True or str(value).strip().lower() in ("1", "true", "on", "sim", "yes")


# Cada parse_* valida os dados vindos da tela e serve tanto para cadastrar (POST) quanto para editar (PUT).
VARIABLE_TYPES = ("Ações", "FIIs", "ETF", "BDR")


def parse_investment(d):
    inv_type = get_text(d, "type", "Tipo")
    if inv_type not in INVESTMENT_TYPES:
        raise ValidationError("Tipo: opção inválida.")
    if inv_type in VARIABLE_TYPES:
        # Renda variável: o valor aplicado é quantidade x preço pago. Sem preço ao vivo, o saldo não rende.
        quantity = get_num(d, "quantity", "Quantidade", minimum=0, exclusive=True)
        price = get_num(d, "unit_price", "Preço pago", minimum=0, exclusive=True)
        return (
            get_text(d, "name", "Nome"), inv_type, round(quantity * price, 2),
            get_date(d, "date", "Data da compra"), "FIXO", 0.0, "",
            get_text(d, "institution", "Instituição", required=False), quantity, price,
        )
    indexer = get_text(d, "index", "Indexador")
    if indexer not in INDEXERS:
        raise ValidationError("Indexador: opção inválida.")
    return (
        get_text(d, "name", "Nome"),
        inv_type,
        get_num(d, "amount", "Valor aplicado", minimum=0, exclusive=True),
        get_date(d, "date", "Data da aplicação"),
        indexer,
        get_num(d, "rate", "Taxa", minimum=0),
        get_date(d, "maturity", "Vencimento", required=False),
        get_text(d, "institution", "Instituição", required=False),
        None, None,
    )


def parse_transaction(d):
    kind = get_text(d, "kind", "Tipo")
    if kind not in ("income", "expense"):
        raise ValidationError("Tipo: opção inválida.")
    return (
        get_text(d, "description", "Descrição"),
        kind,
        get_text(d, "category", "Categoria", max_len=60),
        get_num(d, "amount", "Valor", minimum=0, exclusive=True),
        get_date(d, "date", "Data"),
    )


def parse_goal(d):
    return (
        get_text(d, "name", "Nome da meta"),
        get_num(d, "target", "Valor desejado", minimum=0, exclusive=True),
        get_num(d, "saved", "Valor já guardado", minimum=0, default=0),
        1 if as_bool(d.get("auto")) else 0,
    )


def not_found_or_ok(cur):
    if cur.rowcount == 0:
        return jsonify(error="Registro não encontrado."), 404
    return jsonify(ok=True)


@app.post("/api/investments")
@login_required
def add_investment():
    values = parse_investment(payload_dict())
    db = get_db()
    cur = db.execute(
        "INSERT INTO investments(user_id, name, type, amount, date, indexer, rate, maturity, institution, "
        "quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (g.user["id"], *values),
    )
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/api/investments/<int:row_id>")
@login_required
def edit_investment(row_id):
    values = parse_investment(payload_dict())
    db = get_db()
    cur = db.execute(
        "UPDATE investments SET name = ?, type = ?, amount = ?, date = ?, indexer = ?, rate = ?, "
        "maturity = ?, institution = ?, quantity = ?, unit_price = ? WHERE id = ? AND user_id = ?",
        (*values, row_id, g.user["id"]),
    )
    db.commit()
    return not_found_or_ok(cur)


@app.post("/api/transactions")
@login_required
def add_transaction():
    values = parse_transaction(payload_dict())
    db = get_db()
    cur = db.execute(
        "INSERT INTO transactions(user_id, description, kind, category, amount, date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (g.user["id"], *values),
    )
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/api/transactions/<int:row_id>")
@login_required
def edit_transaction(row_id):
    values = parse_transaction(payload_dict())
    db = get_db()
    cur = db.execute(
        "UPDATE transactions SET description = ?, kind = ?, category = ?, amount = ?, date = ? "
        "WHERE id = ? AND user_id = ?",
        (*values, row_id, g.user["id"]),
    )
    db.commit()
    return not_found_or_ok(cur)


@app.post("/api/goals")
@login_required
def add_goal():
    values = parse_goal(payload_dict())
    db = get_db()
    cur = db.execute(
        "INSERT INTO goals(user_id, name, target, saved, auto) VALUES (?, ?, ?, ?, ?)",
        (g.user["id"], *values),
    )
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@app.put("/api/goals/<int:row_id>")
@login_required
def edit_goal(row_id):
    values = parse_goal(payload_dict())
    db = get_db()
    cur = db.execute(
        "UPDATE goals SET name = ?, target = ?, saved = ?, auto = ? WHERE id = ? AND user_id = ?",
        (*values, row_id, g.user["id"]),
    )
    db.commit()
    return not_found_or_ok(cur)


@app.patch("/api/goals/<int:row_id>")
@login_required
def update_goal(row_id):
    d = payload_dict()
    if "auto" not in d:
        raise ValidationError("Nada para atualizar.")
    db = get_db()
    cur = db.execute(
        "UPDATE goals SET auto = ? WHERE id = ? AND user_id = ?",
        (1 if as_bool(d["auto"]) else 0, row_id, g.user["id"]),
    )
    db.commit()
    return not_found_or_ok(cur)


def delete_row(table, row_id):
    # só apaga se o registro for do usuário logado
    db = get_db()
    cur = db.execute(f"DELETE FROM {table} WHERE id = ? AND user_id = ?", (row_id, g.user["id"]))
    db.commit()
    return not_found_or_ok(cur)


@app.delete("/api/investments/<int:row_id>")
@login_required
def delete_investment(row_id):
    return delete_row("investments", row_id)


@app.delete("/api/transactions/<int:row_id>")
@login_required
def delete_transaction(row_id):
    return delete_row("transactions", row_id)


@app.delete("/api/goals/<int:row_id>")
@login_required
def delete_goal(row_id):
    return delete_row("goals", row_id)


@app.put("/api/settings")
@login_required
def update_settings():
    d = payload_dict()
    cdi = get_num(d, "cdi", "CDI de referência", minimum=0)
    if cdi > 100:
        raise ValidationError("CDI de referência: use um valor até 100.")
    db = get_db()
    db.execute("UPDATE users SET cdi = ? WHERE id = ?", (cdi, g.user["id"]))
    db.commit()
    return jsonify(cdi=cdi)


@app.post("/api/simulate")
@login_required
def api_simulate():
    d = payload_dict()
    initial = get_num(d, "initial", "Valor inicial", minimum=0, default=0)
    monthly = get_num(d, "monthly", "Aporte mensal", minimum=0, default=0)
    rate = get_num(d, "rate", "Rentabilidade anual", minimum=0, default=0)
    years = int(min(50, max(1, get_num(d, "years", "Prazo", default=1))))
    final, deposits, interest = simulate(initial, monthly, rate, years)
    return jsonify(final=round(final, 2), deposits=round(deposits, 2), interest=round(interest, 2))


init_db()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    # O modo debug só liga quando o app está acessível apenas neste computador.
    app.run(host=host, port=port, debug=host in ("127.0.0.1", "localhost"))
