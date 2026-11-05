# Colocar o site no ar (GitHub + PythonAnywhere)

O GitHub guarda o código. Quem **roda** o site é o PythonAnywhere, que puxa o código do GitHub.
Troque `SEUUSUARIO` pelo seu usuário do PythonAnywhere e `SEUGITHUB/REPOSITORIO` pelo seu repositório.

## 1. Subir o código para o GitHub

1. Em https://github.com/new crie o repositório (marque **Public**, sem README).
2. Clique em **uploading an existing file** e arraste `app.py`, `requirements.txt`, `README.md`,
   `DEPLOY.md`, `.gitignore` e a pasta `templates`.
3. **Nunca envie** `vital.db`, `secret.key` ou `.venv` (têm senhas e a chave do login).
4. Clique em **Commit changes**.

## 2. Criar o site no PythonAnywhere

1. Crie a conta gratuita em https://www.pythonanywhere.com.
2. Abra um **Bash console** (aba Consoles) e rode:
   ```
   git clone https://github.com/SEUGITHUB/REPOSITORIO.git
   mkvirtualenv --python=python3.12 meuenv
   cd REPOSITORIO
   pip install -r requirements.txt
   ```
   Se o clone falhar, envie o zip pela aba **Files** e rode `unzip` no console.
   Use no `--python` a mesma versão de Python que escolher no passo seguinte.
3. Aba **Web** → **Add a new web app** → **Manual configuration** → escolha a versão de Python.
4. Preencha na aba Web:
   - **Source code:** `/home/SEUUSUARIO/REPOSITORIO`
   - **Virtualenv:** `/home/SEUUSUARIO/.virtualenvs/meuenv`
5. Abra o **arquivo WSGI** (link na aba Web), apague tudo e cole:
   ```python
   import sys, os
   path = '/home/SEUUSUARIO/REPOSITORIO'
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ['HTTPS'] = '1'
   from app import app as application
   ```
6. Ligue **Force HTTPS**, clique em **Reload** e abra `SEUUSUARIO.pythonanywhere.com`.

## 3. Antes de apresentar

- Crie sua conta no site e cadastre dados de exemplo (o banco do servidor começa vazio).
- Na aba Web, clique no botão de **estender o prazo** do site (o gratuito expira se ficar sem renovar).
- Não use dados financeiros reais: qualquer pessoa com o link pode criar conta.

## 4. Atualizar depois de mudar o código

1. Suba o arquivo novo no GitHub (mesmo nome, substitui).
2. No Bash console: `cd REPOSITORIO && git pull`
3. Aba Web → **Reload**.

O `vital.db` fica só no servidor e não é afetado pelo `git pull`.
