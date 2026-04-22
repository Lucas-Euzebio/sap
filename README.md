# SAP Cobranças - Projeto Zeus Agrotech

Este repositório contém um protótipo de acompanhamento de contas a receber e contas recebidas integrado ao SAP Business One via Service Layer.

## O que o projeto faz

- Sincroniza notas fiscais de saída abertas do SAP (`Invoices`).
- Sincroniza pagamentos recebidos do SAP (`IncomingPayments`).
- Grava os dados em um banco PostgreSQL local.
- Exibe informações de cliente e notas em um frontend simples com FastAPI.
- Permite registrar histórico e observações de cobrança.

## Estrutura principal

- `api.py` — aplicação FastAPI com rotas REST e frontend embarcado.
- `app/config.py` — configuração e leitura de variáveis de ambiente.
- `app/db.py` — conexão com PostgreSQL.
- `app/sap.py` — autenticação no SAP Service Layer, chamada de endpoints e resolução de dados.
- `app/sync.py` — lógica de sincronização de notas e recebimentos.
- `setup_db.py` — cria o banco e as tabelas `notas_cobranca`, `observacoes_cliente` e `historico_cobranca`.
- `sync_banco.py` — entrypoint para sincronizar `Invoices`.
- `sync_recebidas.py` — entrypoint para sincronizar `IncomingPayments`.
- `static/index.html` — interface cliente/nota em HTML/JS.
- `dumps/` — pasta para armazenar saídas JSON dos scripts de inspeção.
- `.gitignore` — arquivos ignorados pelo Git.
- `AI_MODELS_GUIDE.md` — guia interno para uso de modelos de IA.

## Variáveis de ambiente necessárias

No arquivo `.env` ou no ambiente do servidor, defina:

```env
COMPANY_DB=
USERNAME=
PASSWORD=
SAP_URL=
DB_HOST=localhost
DB_PORT=5432
DB_NAME=sap_cobrancas
DB_USER=postgres
DB_PASS=postgres
```

## Como usar

### 1. Configurar o ambiente

1.1. Clone ou navegue até o diretório raiz do projeto:
```bash
cd /caminho/para/sap
```

1.2. Crie um ambiente virtual Python:
```bash
python3 -m venv venv
```

1.3. Ative o ambiente virtual:
```bash
source venv/bin/activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto com as variáveis necessárias:

```bash
cp .env.example .env  # se existir um arquivo de exemplo
# Ou edite manualmente o arquivo .env com suas credenciais
```

### 4. Criar o banco de dados e tabelas

```bash
python setup_db.py
```

Isso criará:
- Banco de dados `sap_cobrancas`
- Tabela `notas_cobranca` (notas fiscais e acompanhamento)
- Tabela `observacoes_cliente` (observações gerais do cliente)
- Tabela `historico_cobranca` (histórico de ações de cobrança)

### 5. Scripts de consulta (utilitários)

#### 5.1 Consultar Contas a Receber no SAP

```bash
# Sem filtros (lista todas as notas em aberto)
python scripts/tools/get_contas_receber.py

# Filtrar por NFS-e específica
python scripts/tools/get_contas_receber.py --nfse "123456789"

# Filtrar por DocEntry (ID interno)
python scripts/tools/get_contas_receber.py --doc-entry 542

# Filtrar por data de emissão (formato YYYY-MM-DD)
python scripts/tools/get_contas_receber.py --doc-date "2024-01-15"

# Filtrar por data de vencimento
python scripts/tools/get_contas_receber.py --due-date "2024-02-15"

# Filtrar por nome do cliente (busca parcial)
python scripts/tools/get_contas_receber.py --card-name "Acme"

# Combinar múltiplos filtros
python scripts/tools/get_contas_receber.py --card-name "Acme" --doc-date "2024-01-15"
```

#### 5.2 Consultar Contas Recebidas (Pagamentos) no SAP

```bash
# Sem filtros (lista todos os pagamentos não-cancelados)
python scripts/tools/get_contas_recebidas.py

# Filtrar por data do pagamento (formato YYYY-MM-DD)
python scripts/tools/get_contas_recebidas.py --doc-date "2024-02-10"

# Filtrar por nome do cliente
python scripts/tools/get_contas_recebidas.py --card-name "Raizen"

# Combinar filtros
python scripts/tools/get_contas_recebidas.py --card-name "Raizen" --doc-date "2024-02-10"
```

#### 5.3 Inspecionar campos de uma Invoice (Nota Fiscal)

```bash
# Sem argumentos: busca a primeira nota aberta e salva em dumps/sap_fields_dump.json
python scripts/tools/print_invoice_fields.py

# Com DocEntry específico: busca aquela nota exata
# Variável: DocEntry (ID interno da nota no SAP, obtido via get_contas_receber.py)
python scripts/tools/print_invoice_fields.py 542

# Outputs: dumps/sap_fields_dump.json com todos os campos disponíveis
```

#### 5.4 Inspecionar campos de um Pagamento (IncomingPayment)

```bash
# Sem argumentos: lista os últimos 50 pagamentos não-cancelados
python scripts/tools/print_incoming_payment_fields.py

# Com DocEntry de uma Invoice: mostra apenas os pagamentos que baixaram aquela nota
# Variável: DocEntry (ID interno da nota no SAP que foi paga)
python scripts/tools/print_incoming_payment_fields.py 542

# Outputs: dumps/sap_incoming_dump.json com todos os pagamentos encontrados
```

### 6. Sincronizar dados do SAP para o banco local

#### 6.1 Sincronizar Notas em Aberto (Invoices)

```bash
# Sincronizar todas as notas em aberto
python sync_banco.py

# Sincronizar apenas notas criadas a partir de uma data
# Variável: --since-date (formato YYYY-MM-DD)
python sync_banco.py --since-date "2024-01-01"
```

Importa todas as notas fiscais abertas do SAP para a tabela `notas_cobranca`.

#### 6.2 Sincronizar Pagamentos Recebidos (IncomingPayments)

```bash
# Sincronizar todos os pagamentos confirmados
python sync_recebidas.py

# Sincronizar apenas pagamentos recebidos a partir de uma data
# Variável: --since-date (formato YYYY-MM-DD)
python sync_recebidas.py --since-date "2024-01-01"
```

Atualiza notas marcando como "Pagamento Confirmado" quando um pagamento é detectado no SAP.

### 7. Rodar o servidor da API

```bash
uvicorn api:app --reload
```

O servidor iniciará em `http://127.0.0.1:8000`.

- Frontend HTML embarcado: `http://127.0.0.1:8000`
- Documentação interativa: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

### 8. Workflow recomendado

1. Configure o .env com suas credenciais SAP
2. Execute `python setup_db.py` uma única vez
3. Rode `python get_contas_receber.py` ou `python get_contas_recebidas.py` para validar conexão com SAP
4. Execute `python sync_banco.py` seguido de `python sync_recebidas.py` para popular o banco inicial
5. Inicie a API com `uvicorn api:app --reload`
6. Agora você pode clicar nos clientes e notas no frontend para marcar pagamentos, observações e histórico


## Mapeamento de campos SAP para `notas_cobranca`

### Dados identificadores da nota

- **`doc_entry`** — Identificador interno do SAP  
  Origem: `Invoices.DocEntry` / `IncomingPayments.PaymentInvoices[].DocEntry`

- **`doc_num`** — Número do documento SAP da nota  
  Origem: `Invoices.DocNum`

- **`numero_documento`** — Sequência do documento (ou `S/N` quando ausente)  
  Origem: `Invoices.SequenceSerial`

- **`nfse`** — Número da NFS-e  
  Origem: `Invoices.U_TX_NDfe` (campo customizado)

### Dados do cliente

- **`card_code`** — Código do cliente no SAP  
  Origem: `Invoices.CardCode` / `IncomingPayments.CardCode`

- **`card_name`** — Razão social do cliente  
  Origem: `Invoices.CardName` / `IncomingPayments.CardName`

- **`nome_fantasia`** — Nome fantasia do cliente  
  Origem: `BusinessPartners.CardForeignName` (via endpoint `BusinessPartners`)

- **`cnpj_cpf`** — Identificação fiscal  
  Origem: `Invoices.TaxExtension.TaxId0` ou `TaxExtension.TaxId4` ou `Invoices.VATRegNum`

### Datas e valores da nota

- **`data_emissao`** — Data de emissão da nota  
  Origem: `Invoices.DocDate`

- **`data_vencimento`** — Data de vencimento  
  Origem: `Invoices.DocDueDate`

- **`valor_total`** — Valor total bruto da nota  
  Origem: `Invoices.DocTotal`

- **`saldo_pendente`** — Valor restante do título (saldo em aberto)  
  Origem: `Invoices.DocTotal`, `PaidToDate`, `WTApplied`, `WTAmount`, `DocumentLines`  
  **Fórmula:**
  ```
  se WTApplied > 0:
    saldo = DocTotal - WTApplied - PaidToDate
  senão, se WTAmount > 0:
    CSLL_PIS_COFINS = SUM(LineTotal) × 0.0465
    saldo = DocTotal - CSLL_PIS_COFINS - PaidToDate
  senão:
    saldo = DocTotal - PaidToDate
  ```

### Dados de pagamento e contábeis

- **`conta_razao_codigo`** — Conta contábil do pagamento  
  Origem: `IncomingPayments.TransferAccount` / `CashAccount` / `CheckAccount` / `BoeAccount` / `ControlAccount`

- **`conta_razao_nome`** — Descrição da conta contábil  
  Origem: `ChartOfAccounts.Name` (via endpoint `ChartOfAccounts`)

- **`banco`** — Dados bancários do recebimento  
  Origem: `IncomingPayments.BankCode`, `BankAccount`, `PayToBankBranch`, `PayToBankAccountNo`, `PayToCode`  
  *Composto por múltiplos campos do SAP, não é um campo nativo único.*

- **`data_pagamento`** — Data do pagamento confirmado  
  Origem: `IncomingPayments.DocDate`

### Acompanhamento de cobrança

- **`status_cobranca`** — Status do acompanhamento  
  Valores: `'Pendente'`, `'Pagamento Confirmado'`, `'Promessa de Pagamento'`  
  Calculado pelo sistema

- **`responsavel`** — Responsável pela tratativa  
  Definido manualmente via API/Frontend

- **`observacoes`** — Anotações sobre a cobrança  
  Definido manualmente via API/Frontend

- **`data_promessa`** — Data da promessa de pagamento  
  Definido manualmente via API/Frontend

- **`data_atualizacao`** — Timestamp da última alteração  
  Gerado automaticamente pelo sistema

## Pontos importantes

- O campo `banco` é um campo textual composto, não um campo nativo único do SAP.
- O `setup_db.py` agora cria as tabelas `notas_cobranca`, `observacoes_cliente` e `historico_cobranca`.
- O projeto usa o `IncomingPayments` para detectar pagamentos já confirmados e marcar notas como baixadas.
- O projeto usa `Invoices` para manter o cadastro das notas em aberto e calcular saldos.

## Estrutura de SAP usada

- `Invoices` — notas fiscais / contas a receber.
- `IncomingPayments` — registros de recebimento financeiro.
- `BusinessPartners` — informações de parceiro de negócios (nome fantasia).
- `ChartOfAccounts` — nome da conta contábil para o campo conta razão.

## Notas finais

Este README deve ser atualizado sempre que novas colunas do banco ou novos campos SAP forem adicionados ao fluxo de sincronização.
