# VITAL GARANHAO

Controle financeiro com **Flask (Python) + SQLite**, com **login e cadastro de usuários**.
O Python guarda os dados e faz os cálculos (rendimento, IR, IOF, simulador); o HTML cuida só da tela.
Cada pessoa vê apenas os próprios investimentos, movimentações e metas.

## Como rodar

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Abra http://localhost:5000. Na primeira vez, clique em **Criar conta**.

> Dados de uma versão antiga (sem login) ficam para a **primeira conta criada**.

## Estrutura

```
vital-garanhao/
├── app.py                # servidor Flask, login, API, cálculos e banco SQLite
├── requirements.txt
├── DEPLOY.md             # passo a passo para publicar (GitHub + PythonAnywhere)
├── setup_pythonanywhere.sh   # instala e configura o site no PythonAnywhere
├── seed_demo.py          # cria uma conta de demonstração com dados de exemplo
├── templates/
│   ├── index.html        # painel (exige login)
│   └── login.html        # entrar / criar conta
├── vital.db              # banco de dados (criado na primeira execução)
└── secret.key            # chave que assina o login (criada na primeira execução)
```

Não compartilhe `vital.db` nem `secret.key`.

## Rotas da API

| Método | Rota | O que faz |
|--------|------|-----------|
| POST | `/api/register` | Cria conta e já entra |
| POST | `/api/login` | Entra |
| POST | `/api/logout` | Sai |
| GET | `/api/summary` | Tudo já calculado do usuário logado |
| POST | `/api/investments` | Cadastra investimento |
| PUT | `/api/investments/<id>` | Edita investimento |
| DELETE | `/api/investments/<id>` | Exclui investimento |
| POST | `/api/transactions` | Cadastra receita/despesa |
| PUT | `/api/transactions/<id>` | Edita movimentação |
| DELETE | `/api/transactions/<id>` | Exclui movimentação |
| POST | `/api/goals` | Cria meta |
| PUT | `/api/goals/<id>` | Edita meta |
| PATCH | `/api/goals/<id>` | Liga/desliga o acompanhamento automático da meta |
| DELETE | `/api/goals/<id>` | Exclui meta |
| PUT | `/api/settings` | Altera o CDI de referência |
| POST | `/api/simulate` | Simulador de juros compostos |

Todas, exceto cadastro e login, exigem estar logado.

## Segurança (o que já está feito)

- Senhas guardadas com hash (nunca o texto da senha).
- Cookie de sessão protegido (HttpOnly, SameSite) e válido por 7 dias.
- Bloqueio temporário após 5 senhas erradas em 5 minutos.
- Cada consulta é filtrada pelo usuário logado, então ninguém acessa dados de outra conta.

## Para outras pessoas usarem pela internet

Rodando em `localhost`, só quem está neste computador acessa. Para deixar o site no ar sem o
seu computador (GitHub + PythonAnywhere), siga o passo a passo do arquivo **DEPLOY.md**.
Em outros servidores, é preciso:

- use **HTTPS** e defina `HTTPS=1` para o cookie só viajar protegido;
- rode com um servidor de produção (por exemplo `gunicorn app:app`), nunca com `python app.py`;
- defina uma `SECRET_KEY` própria e faça backup do `vital.db`.

Para zerar tudo, pare o servidor e apague `vital.db`.

## Regras de imposto usadas

- **LCI, LCA e Poupança:** isentos de IR e IOF (pessoa física).
- **Demais investimentos:** IR pela tabela regressiva (22,5% até 180 dias, 20% até 360, 17,5% até 720, 15% acima) e IOF pela tabela oficial nos primeiros 29 dias.
- Ações, FIIs e ETF têm regras próprias na vida real; aqui seguem a mesma tabela, como simplificação.

> Versão demonstrativa. Cálculos de IR/IOF são estimativas simplificadas e não constituem
> recomendação de investimento.
