import os
import sys
import json
import requests
from dotenv import load_dotenv
from app.sap import login_sap

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def dump_incoming_payment(doc_entry_invoice=None):
    """
    Busca pagamentos no endpoint IncomingPayments e faz o dump completo.
    Se doc_entry_invoice for informado, filtra apenas os pagamentos que referenciam aquela nota.
    """
    session_id = login_sap()
    if not session_id:
        print("Falha na autenticação.")
        return

    load_dotenv()
    sap_url = os.getenv('SAP_URL').rstrip('/')
    cookies = {"B1SESSION": session_id}

    endpoint = f"{sap_url}/b1s/v1/IncomingPayments"

    params = {
        "$filter": "Cancelled eq 'tNO'",
        "$orderby": "DocNum desc",
    }
    headers = {"Prefer": "odata.maxpagesize=50"}

    print(f"🔄 Buscando IncomingPayments (últimos 50 não cancelados)...")
    res = requests.get(endpoint, cookies=cookies, params=params, headers=headers, verify=False)

    if res.status_code != 200:
        print(f"❌ Erro: {res.status_code} - {res.text}")
        return

    pagamentos = res.json().get("value", [])
    print(f"✅ {len(pagamentos)} pagamentos encontrados.\n")

    resultados = []
    encontrou = False
    for pg in pagamentos:
        invoices = pg.get("PaymentInvoices", [])

        # Se filtro de DocEntry foi passado, só mostra pagamentos que referenciam essa nota
        if doc_entry_invoice:
            match = any(inv.get("DocEntry") == int(doc_entry_invoice) for inv in invoices)
            if not match:
                continue

        encontrou = True
        resultados.append(pg)
        print("=" * 60)
        print(f"📄 Incoming Payment DocEntry: {pg.get('DocEntry')} | DocNum: {pg.get('DocNum')}")
        print(f"👤 Cliente: {pg.get('CardCode')} - {pg.get('CardName')}")
        print(f"📅 Data Pagamento: {pg.get('DocDate')}")
        print()

        print("=== DUMP COMPLETO DOS CAMPOS (exceto sub-coleções) ===")
        for k, v in pg.items():
            if not isinstance(v, (list, dict)):
                if v is not None and v != 0 and v != "" and v != "tNO":
                    print(f"  {k}: {v}")

        print()
        print("=== PaymentInvoices (Notas Baixadas) ===")
        for inv in invoices:
            print(f"  DocEntry: {inv.get('DocEntry')} | InvoiceType: {inv.get('InvoiceType')}")
            for k, v in inv.items():
                if not isinstance(v, (list, dict)) and v is not None and v != 0 and v != "":
                    print(f"    {k}: {v}")
            print()

        print("=== DUMP JSON COMPLETO ===")
        print(json.dumps(pg, indent=2, ensure_ascii=False))
        print("=" * 60)
        print()

    if not encontrou:
        if doc_entry_invoice:
            print(f"⚠️  Nenhum IncomingPayment encontrado referenciando o DocEntry {doc_entry_invoice}.")
            print("    A nota pode ainda não ter sido paga, ou o pagamento foi cancelado.")
        else:
            print("Nenhum pagamento encontrado.")
    else:
        output_file = "dumps/sap_incoming_dump.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(resultados, f, indent=4, ensure_ascii=False)
        print(f"\n💾 Dump salvo em: {output_file}  ({len(resultados)} pagamento(s))")


if __name__ == "__main__":
    entry = sys.argv[1] if len(sys.argv) > 1 else None
    if entry:
        print(f"🔍 Filtrando pagamentos que referenciam a nota DocEntry: {entry}\n")
    dump_incoming_payment(entry)
