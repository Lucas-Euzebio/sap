import os
import sys
import json
import requests
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Adiciona a raiz do projeto ao sys.path para permitir imports do módulo 'app'
root_path = str(Path(__file__).resolve().parent.parent.parent)
if root_path not in sys.path:
    sys.path.append(root_path)

from app.sap import login_sap

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def dump_incoming_payment(doc_num_pag=None, doc_num_inv=None):
    """
    Busca pagamentos no endpoint IncomingPayments e faz o dump completo.
    """
    session_id = login_sap()
    if not session_id:
        print("Falha na autenticação.")
        return

    load_dotenv()
    sap_url = os.getenv('SAP_URL').rstrip('/')
    cookies = {"B1SESSION": session_id}

    endpoint = f"{sap_url}/b1s/v1/IncomingPayments"

    filters = ["Cancelled eq 'tNO'"]
    if doc_num_pag:
        filters.append(f"DocNum eq {doc_num_pag}")
    
    # Se o filtro for por Nota Fiscal, primeiro precisamos achar o DocEntry dela se o usuário passou DocNum
    # Mas para simplificar, se for doc_num_inv, vamos buscar todos os pagamentos e filtrar localmente no loop 
    # ou fazer uma sub-query se o SAP permitisse. Vamos filtrar localmente para ser mais robusto.

    # Se o filtro for por Número de Invoice, buscamos ela e tentamos achar o ReceiptNum (Link direto)
    target_doc_entry_inv = None
    if doc_num_inv:
        print(f"🔍 Localizando a Invoice #{doc_num_inv} no SAP...")
        # --num-inv representa o número visível na tela do SAP (SequenceSerial), NÃO o DocNum interno
        filter_str = f"SequenceSerial eq {doc_num_inv}"
        print(f"📡 Filtro enviado: {filter_str}")
        
        res_inv = requests.get(
            f"{sap_url}/b1s/v1/Invoices", 
            cookies=cookies, 
            params={"$filter": filter_str}, # Removido $select para evitar o erro de propriedade inválida
            verify=False
        )
        
        if res_inv.status_code == 200:
            value = res_inv.json().get("value", [])
            if value:
                inv_data = value[0]
                target_doc_entry_inv = inv_data["DocEntry"]
                receipt_num = inv_data.get("ReceiptNum")
                
                print(f"🎯 Invoice localizada! DocEntry: {target_doc_entry_inv} | DocNum: {inv_data.get('DocNum')} | Num: {inv_data.get('SequenceSerial')}")
                
                if receipt_num and receipt_num > 0:
                    print(f"🔗 Nota vinculada ao Recibo (IncomingPayment) DocEntry: {receipt_num}")
                    endpoint = f"{sap_url}/b1s/v1/IncomingPayments({receipt_num})"
                    filters = [] 
                    params = {}
                else:
                    card_code = inv_data.get("CardCode")
                    if card_code:
                        print(f"⚠️  Sem ReceiptNum direto. Filtrando pagamentos do cliente {card_code}...")
                        filters.append(f"CardCode eq '{card_code}'")
                    else:
                        print("⚠️  Sem ReceiptNum e sem CardCode. A busca pode ser lenta (varredura ampla).")
            else:
                print(f"⚠️  Invoice {doc_num_inv} não encontrada nos resultados do SAP.")
                return
        else:
            print(f"❌ Erro na busca da Invoice: {res_inv.status_code} - {res_inv.text}")
            return

    if filters:
        params = {
            "$filter": " and ".join(filters),
            "$orderby": "DocNum desc",
        }
    
    headers = {"Prefer": "odata.maxpagesize=500"}

    print(f"🔄 Consultando SAP...")
    res = requests.get(endpoint, cookies=cookies, params=params, headers=headers, verify=False)

    if res.status_code != 200:
        print(f"❌ Erro: {res.status_code} - {res.text}")
        return

    data = res.json()
    if "value" in data:
        pagamentos = data.get("value", [])
    else:
        # Se fomos direto pelo ID (IncomingPayments(ID)), ele retorna o objeto direto, não uma lista
        pagamentos = [data]

    print(f"✅ {len(pagamentos)} registro(s) carregado(s). Iniciando processamento...\n")

    resultados = []
    encontrou = False

    for pg in pagamentos:
        invoices = pg.get("PaymentInvoices", [])

        if target_doc_entry_inv:
            match = any(inv.get("DocEntry") == target_doc_entry_inv for inv in invoices)
            if not match:
                continue

        encontrou = True
        resultados.append(pg)
        print("=" * 60)
        print(f"📄 Incoming Payment DocEntry: {pg.get('DocEntry')} | DocNum: {pg.get('DocNum')}")
        print(f"👤 Cliente: {pg.get('CardCode')} - {pg.get('CardName')}")
        print(f"📅 Data Pagamento: {pg.get('DocDate')}")
        print()

        print("=== DUMP COMPLETO DOS CAMPOS (só preenchidos) ===")
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
        print("Nenhum pagamento encontrado com os critérios informados.")
    else:
        os.makedirs("dumps", exist_ok=True)
        output_file = "dumps/sap_incoming_dump.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(resultados, f, indent=4, ensure_ascii=False)
        print(f"\n💾 Dump salvo em: {output_file} ({len(resultados)} pagamento(s))")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspeciona campos brutos de um Recebimento (Incoming Payment) no SAP")
    parser.add_argument("--doc-num-pag", type=int, help="Número do Pagamento (DocNum) no SAP")
    parser.add_argument("--doc-num-inv", type=int, help="Número Interno da Fatura (DocNum) SAP")
    parser.add_argument("--num-inv", type=int, help="Número que aparece na tela da Fatura (SequenceSerial)")
    
    args = parser.parse_args()
    dump_incoming_payment(doc_num_pag=args.doc_num_pag, doc_num_inv=args.doc_num_inv or args.num_inv)
