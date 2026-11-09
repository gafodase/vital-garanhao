# Histórico de versões

Tudo o que mudou no projeto, da primeira versão até agora. A mais recente vem primeiro.

## v1.7: Gráfico, meta de renda e recuperação de senha (09/11/2026)
- Aba Proventos: **gráfico de barras** com o que você recebeu nos últimos 12 meses.
- **Meta de renda passiva por mês**: linha tracejada no gráfico e barra de progresso.
- **Recuperação de senha** sem e-mail: código mostrado uma vez ao criar a conta, tela "Esqueci minha senha" e botão para gerar um novo código.
- Tentativas erradas de recuperação também são limitadas (5 em 5 minutos).

## v1.6: Proventos (09/11/2026)
- Nova aba **Proventos**: média por mês, total já recebido e valor a receber de cada ação, FII, ETF e BDR.
- Tabela mês a mês com tudo o que já caiu, contando só o que foi pago depois da sua compra.
- Dados da brapi.dev; se não vierem, a aba avisa em vez de mostrar números errados.
- Quando não vêm dados, a aba mostra o motivo (ex.: ativo que exige o token da brapi, ou nome sem o código do ativo).

## v1.5: Cotações ao vivo (08/11/2026)
- Ações, FIIs, ETFs e BDRs mostram o **preço de hoje** (brapi.dev) e o **lucro ou prejuízo**, em vermelho quando perde.
- Cotação guardada por 15 minutos; se falhar, o ativo continua pelo valor pago e o site não quebra.
- Gráfico de evolução e metas automáticas usam o valor atualizado.
- Token opcional da brapi (`BRAPI_TOKEN`) explicado no `DEPLOY.md`.

## v1.4: Quantidade e preço pago (08/11/2026)
- Ao escolher **Ações, FIIs, ETF ou BDR**, o formulário pede quantidade comprada e preço por unidade.
- Somem taxa, indexador, valor aplicado e vencimento, que só servem para renda fixa.
- O valor investido é calculado (quantidade × preço) e aparece como "Total investido".

## v1.3: Lista da B3 (08/11/2026)
- Lista fixa de **ações, FIIs, ETFs e BDRs** da B3 (cerca de 2.700 ativos, cadastro de 05/11/2026) no arquivo `b3_ativos.json`.
- Ao escolher o tipo, aparece a lista completa daquele tipo, com filtro por código ou nome.
- Novo tipo de investimento: **BDR**.

## v1.2: README (08/11/2026)
- Link do site no ar no topo do README.
- "Como rodar" explicado como opcional.

## v1.1: Publicação online (05/11/2026)
- Instalação automática no PythonAnywhere (`setup_pythonanywhere.sh`) e passo a passo no `DEPLOY.md`.
- `seed_demo.py`: cria uma conta de demonstração com dados de exemplo.
- Correção: o script achava o arquivo de configuração só com usuário em minúsculas.

## v1.0: Primeira versão (05/11/2026)
- Controle financeiro com **Flask + SQLite**: o Python guarda os dados e faz os cálculos; o HTML cuida da tela.
- **Login e cadastro**, com dados separados por usuário, senha com hash e bloqueio após 5 erros.
- Painel com patrimônio, investimentos, receitas e despesas, simulador e metas.
- **Metas automáticas**: acompanham o total da carteira.
- Edição de investimentos, movimentações e metas.
- Regras de imposto: IR regressivo e IOF; LCI, LCA e Poupança isentos.
- Gráfico de evolução do patrimônio.

