from .db import get_db_connection
from .sap import login_sap, get_account_name, get_nome_fantasia, get_invoice_info
from .config import get_sap_url
from .utils import normalize_date

import requests


def sync_invoices(since_date=None):
    session_id = login_sap()
    if not session_id:
        return {"inseridos": 0, "atualizados": 0}

    endpoint = f"{get_sap_url()}/b1s/v1/Invoices"
    filters = ["DocumentStatus eq 'bost_Open'"]
    if since_date:
        filters.append(f"UpdateDate ge '{since_date}'")

    params = {
        "$filter": " and ".join(filters),
        "$orderby": "DocNum desc",
        "$select": "DocNum,DocEntry,CardCode,CardName,DocDate,DocDueDate,DocTotal,PaidToDate,WTApplied,WTAmount,SequenceSerial,VATRegNum,TaxExtension,U_TX_NDfe,DocumentLines"
    }
    headers = {"Prefer": "odata.maxpagesize=1000"}

    conn = get_db_connection()
    cursor = conn.cursor()

    query_upsert = """
        INSERT INTO notas_cobranca (
            doc_entry, doc_num, numero_documento, nfse, card_code, card_name, nome_fantasia, 
            cnpj_cpf, data_emissao, data_vencimento, valor_total, saldo_pendente, data_atualizacao
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, 
            %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
        )
        ON CONFLICT (doc_entry) 
        DO UPDATE SET 
            saldo_pendente = EXCLUDED.saldo_pendente,
            valor_total = EXCLUDED.valor_total,
            data_vencimento = EXCLUDED.data_vencimento,
            data_atualizacao = CURRENT_TIMESTAMP;
    """

    registros_inseridos = 0
    registros_atualizados = 0

    response = requests.get(endpoint, headers=headers, params=params, cookies={"B1SESSION": session_id}, verify=False)
    if response.status_code != 200:
        print(f"❌ Erro ao consultar SAP: {response.status_code} - {response.text}")
        return {"inseridos": 0, "atualizados": 0}

    contas = response.json().get("value", [])
    for conta in contas:
        doc_entry = conta.get("DocEntry")
        doc_num = conta.get("DocNum")
        numero_documento = conta.get("SequenceSerial") or "S/N"
        nfse = conta.get("U_TX_NDfe") or "S/N"
        card_code = conta.get("CardCode")
        card_name = (conta.get("CardName") or "")[:255]

        tax_ext = conta.get("TaxExtension", {})
        cnpj_cpf = tax_ext.get("TaxId0") or tax_ext.get("TaxId4") or "N/A"
        cnpj_cpf = cnpj_cpf[:20]

        doc_date = normalize_date(conta.get("DocDate"))
        doc_due_date = normalize_date(conta.get("DocDueDate"))

        doc_total = float(conta.get("DocTotal", 0.0))
        paid_to_date = float(conta.get("PaidToDate", 0.0))
        wt_applied = float(conta.get("WTApplied", 0.0))
        wt_amount = float(conta.get("WTAmount", 0.0))

        if wt_applied > 0:
            saldo_pendente = doc_total - wt_applied - paid_to_date
        elif wt_amount > 0:
            line_total = sum(float(line.get("LineTotal", 0.0)) for line in conta.get("DocumentLines", []))
            csll_pis_cofins = line_total * 0.0465
            saldo_pendente = doc_total - csll_pis_cofins - paid_to_date
        else:
            saldo_pendente = doc_total - paid_to_date

        nome_fantasia = get_nome_fantasia(session_id, card_code)[:255]

        cursor.execute(query_upsert, (
            doc_entry, doc_num, numero_documento, nfse, card_code, card_name, nome_fantasia,
            cnpj_cpf, doc_date, doc_due_date, doc_total, saldo_pendente
        ))

        if cursor.rowcount == 1:
            registros_inseridos += 1
        else:
            registros_atualizados += 1

    conn.commit()
    cursor.close()
    conn.close()

    return {"inseridos": registros_inseridos, "atualizados": registros_atualizados}


def sync_recebidas(since_date=None):
    session_id = login_sap()
    if not session_id:
        return 0

    endpoint = f"{get_sap_url()}/b1s/v1/IncomingPayments"
    filters = ["Cancelled eq 'tNO'"]
    if since_date:
        filters.append(f"DocDate ge '{since_date}'")

    params = {
        "$filter": " and ".join(filters),
        "$orderby": "DocNum desc"
    }
    headers = {"Prefer": "odata.maxpagesize=100"}

    conn = get_db_connection()
    cursor = conn.cursor()

    def resolve_conta_razao(pg):
        return (
            pg.get("TransferAccount")
            or pg.get("CashAccount")
            or pg.get("CheckAccount")
            or pg.get("BoeAccount")
            or pg.get("ControlAccount")
            or "N/A"
        )

    def resolve_banco(pg):
        banco_parts = []
        bank_code = pg.get("BankCode") or pg.get("PayToBankCode")
        if bank_code:
            banco_parts.append(f"Banco: {bank_code}")
        if pg.get("BankAccount"):
            banco_parts.append(f"Conta: {pg.get('BankAccount')}")
        if pg.get("PayToBankBranch"):
            banco_parts.append(f"Agência: {pg.get('PayToBankBranch')}")
        if pg.get("PayToBankAccountNo"):
            banco_parts.append(f"Conta Favorecido: {pg.get('PayToBankAccountNo')}")
        if pg.get("PayToCode"):
            banco_parts.append(f"Favorecido: {pg.get('PayToCode')}")
        return " | ".join(banco_parts) if banco_parts else "N/A"

    novos_pagamentos = 0
    response = requests.get(endpoint, cookies={"B1SESSION": session_id}, headers=headers, params=params, verify=False)
    if response.status_code != 200:
        print(f"Erro consultando recebimentos: {response.text}")
        cursor.close()
        conn.close()
        return 0

    pagamentos = response.json().get("value", [])
    for pg in pagamentos:
        data_pagamento = normalize_date(pg.get("DocDate"))
        conta_razao_codigo = resolve_conta_razao(pg)
        conta_razao_nome = get_account_name(session_id, conta_razao_codigo) if conta_razao_codigo not in (None, "N/A") else "N/A"
        banco = resolve_banco(pg)

        for inv in pg.get("PaymentInvoices", []):
            if inv.get("InvoiceType") != "it_Invoice":
                continue

            doc_entry = inv.get("DocEntry")
            cursor.execute("SELECT doc_entry, data_pagamento FROM notas_cobranca WHERE doc_entry = %s", (doc_entry,))
            row = cursor.fetchone()

            if row:
                if row[1] is None:
                    novos_pagamentos += 1
                cursor.execute(
                    """
                    UPDATE notas_cobranca
                    SET saldo_pendente = 0,
                        status_cobranca = 'Pagamento Confirmado',
                        data_pagamento = %s,
                        conta_razao_codigo = %s,
                        conta_razao_nome = %s,
                        banco = %s,
                        data_atualizacao = CURRENT_TIMESTAMP
                    WHERE doc_entry = %s
                    """,
                    (data_pagamento, conta_razao_codigo, conta_razao_nome, banco, doc_entry),
                )
            else:
                info = get_invoice_info(session_id, doc_entry)
                if info:
                    novos_pagamentos += 1
                    nome_fan = get_nome_fantasia(session_id, info["card_code"])[:255]
                    cursor.execute(
                        """
                        INSERT INTO notas_cobranca (
                            doc_entry, doc_num, numero_documento, nfse, card_code, card_name, nome_fantasia,
                            cnpj_cpf, data_emissao, data_vencimento, valor_total, saldo_pendente, conta_razao_codigo,
                            conta_razao_nome, banco, status_cobranca, data_pagamento, data_atualizacao
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, 0, %s,
                            %s, %s, 'Pagamento Confirmado', %s, CURRENT_TIMESTAMP
                        )
                        """,
                        (
                            doc_entry,
                            info["doc_num"],
                            info["numero"],
                            info["nfse"],
                            info["card_code"],
                            info["card_name"],
                            nome_fan,
                            info["cnpj_cpf"][:20],
                            normalize_date(info["doc_date"]),
                            normalize_date(info["due_date"]),
                            float(info["doc_total"] or 0.0),
                            conta_razao_codigo,
                            conta_razao_nome,
                            banco,
                            data_pagamento,
                        ),
                    )

    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Sincronização de Recebimentos Concluída! Total Novos: {novos_pagamentos}")
    return novos_pagamentos
