# Guia de Modelos de IA

Este documento descreve como trabalhar com modelos de IA no contexto deste projeto e manter prompts e configurações organizadas.

## 1. Quando usar IA aqui

- Extrair campos ou mapear dados do SAP para a base local.
- Gerar descrições breves de alterações de código para documentação.
- Sugerir reorganização de código e separação de responsabilidades.
- Criar textos de interface ou guias de uso interno.

## 2. Como formular prompts claros

- Seja específico sobre o objetivo: "Atualize a API para incluir `conta_razao_codigo` e `banco`".
- Indique o arquivo e a camada: backend (`api.py`, `sync_recebidas.py`) ou frontend (`static/index.html`).
- Inclua contexto do banco e do SAP quando relevante.
- Evite perguntas abertas demais sem mostrar o código atual.

## 3. Boas práticas de prompt

- Use termos do domínio:
  - `IncomingPayments`, `Invoices`, `contas recebidas`, `contas a receber`
  - `doc_entry`, `card_code`, `saldo_pendente`, `data_pagamento`
- Peça a criação de funções pequenas e reutilizáveis.
- Solicite separação de responsabilidades:
  - SAP client / config / banco / API / frontend.

## 4. Estrutura de código recomendada

- `app/config.py`: configurações e variáveis de ambiente.
- `app/db.py`: conexão com PostgreSQL.
- `app/login.py`: login no SAP Service Layer.
- `app/sap.py`: chamadas SAP e conversões de dados.
- `app/sync.py`: lógica de sincronização de notas e pagamentos.
- `api.py`: aplicação FastAPI e rotas.

## 5. Segurança e versionamento

- Nunca versionar credenciais em `.env`.
- Adicione ao `.gitignore` arquivos de ambiente e dumps.
- Para produção, use um gerenciador de segredos ou variáveis de ambiente do servidor.

## 6. Checklist antes de pedir IA

- Verifique se há arquivos relevantes no repositório.
- Identifique claramente o comportamento esperado.
- Anexe exemplos de entrada/saída quando possível.
- Peça apenas um tipo de alteração por vez para evitar refactorings grandes automáticos.
