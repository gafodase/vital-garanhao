#!/usr/bin/env bash
# Prepara o site no PythonAnywhere.
# Rode no Bash console, de dentro da pasta do projeto:
#     bash setup_pythonanywhere.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-$HOME/venv-vital}"
PY="${PYTHON:-python3.13}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
USER_NAME="${USER:-$(whoami)}"

# Arquivo de configuração do servidor (criado pela aba Web ao adicionar o site).
WSGI_FILE="${WSGI_FILE:-}"
if [ -z "$WSGI_FILE" ]; then
  WSGI_FILE="$(ls /var/www/"${USER_NAME}"*_wsgi.py 2>/dev/null | head -n 1 || true)"
fi

echo "1/3  Criando o ambiente Python em $VENV_DIR ($("$PY" --version))"
"$PY" -m venv "$VENV_DIR"

echo "2/3  Instalando as dependências"
"$VENV_DIR/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"
# Importar o app cria o banco (vital.db) e a chave de login (secret.key) na primeira vez.
"$VENV_DIR/bin/python" -c "import sys; sys.path.insert(0, '$PROJECT_DIR'); import app"

WSGI_CONTENT="import sys, os
path = '$PROJECT_DIR'
if path not in sys.path:
    sys.path.insert(0, path)
os.environ['HTTPS'] = '1'
from app import app as application
"

echo "3/3  Configurando o servidor"
if [ -n "$WSGI_FILE" ] && [ -w "$WSGI_FILE" ]; then
  printf '%s' "$WSGI_CONTENT" > "$WSGI_FILE"
  touch "$WSGI_FILE"   # avisa o PythonAnywhere para recarregar o site
  echo "     Arquivo de configuração atualizado: $WSGI_FILE"
else
  echo "     Não achei o arquivo de configuração. Na aba Web, abra o link do arquivo WSGI,"
  echo "     apague tudo e cole o texto abaixo:"
  echo "-----------------------------------------------------------------"
  printf '%s' "$WSGI_CONTENT"
  echo "-----------------------------------------------------------------"
fi

cat <<EOF

Quase pronto. Faltam 3 passos na aba Web do PythonAnywhere:
  1. Em "Virtualenv", digite:  $VENV_DIR
  2. Ligue "Force HTTPS".
  3. Clique no botão verde "Reload".

Depois abra:  https://${USER_NAME}.pythonanywhere.com
EOF
