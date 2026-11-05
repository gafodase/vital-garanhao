"""Cria uma conta de demonstração já com dados de exemplo.

Uso:
    python seed_demo.py USUARIO SENHA

Serve para abrir o site na frente de alguém com tudo preenchido (investimentos, movimentações e metas).
Dados fictícios; não use uma senha que você usa em outros lugares.
"""
import sqlite3
import sys
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

import app as A


def main():
    if len(sys.argv) != 3:
        sys.exit("Uso: python seed_demo.py USUARIO SENHA")
    try:
        username = A.normalize_username(sys.argv[1])
        A.validate_password(sys.argv[2])
    except A.ValidationError as err:
        sys.exit(str(err))

    db = sqlite3.connect(A.DB_PATH)
    if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        sys.exit(f"O usuário '{username}' já existe. Escolha outro nome.")

    uid = db.execute(
        "INSERT INTO users(username, password_hash, cdi) VALUES (?, ?, ?)",
        (username, generate_password_hash(sys.argv[2]), A.DEFAULT_CDI),
    ).lastrowid

    today = date.today()
    ago = lambda days: (today - timedelta(days=days)).isoformat()

    db.executemany(
        "INSERT INTO investments(user_id, name, type, amount, date, indexer, rate, maturity, institution) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (uid, "CDB Banco Demo", "CDB", 10000, ago(420), "CDI", 110, "", "Banco Demo"),
            (uid, "LCI Imobiliária", "LCI", 5000, ago(240), "CDI", 95, "", "Banco Demo"),
            (uid, "Tesouro IPCA+", "Tesouro IPCA+", 3000, ago(120), "IPCA", 6, "", "Tesouro Direto"),
            (uid, "Tesouro Selic", "Tesouro Selic", 2000, ago(80), "CDI", 100, "", "Tesouro Direto"),
            (uid, "Fundo Imobiliário", "FIIs", 1500, ago(60), "FIXO", 9, "", "Corretora Demo"),
        ],
    )

    transactions = []
    for month in range(3):
        base = 30 * month
        transactions += [
            (uid, "Salário", "income", "Trabalho", 5200, ago(base + 5)),
            (uid, "Aluguel", "expense", "Moradia", 1500, ago(base + 4)),
            (uid, "Mercado", "expense", "Alimentação", 800, ago(base + 8)),
            (uid, "Transporte", "expense", "Transporte", 250, ago(base + 10)),
            (uid, "Lazer", "expense", "Lazer", 300, ago(base + 14)),
        ]
    db.executemany(
        "INSERT INTO transactions(user_id, description, kind, category, amount, date) VALUES (?, ?, ?, ?, ?, ?)",
        transactions,
    )

    db.executemany(
        "INSERT INTO goals(user_id, name, target, saved, auto) VALUES (?, ?, ?, ?, ?)",
        [
            (uid, "Reserva de emergência", 30000, 0, 1),
            (uid, "Viagem", 8000, 1500, 0),
        ],
    )
    db.commit()
    db.close()
    print(f"Conta '{username}' criada com dados de exemplo. Entre no site com esse usuário e a senha informada.")


if __name__ == "__main__":
    main()
