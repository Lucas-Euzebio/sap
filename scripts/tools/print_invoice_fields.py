import os
import json
import requests
from dotenv import load_dotenv

from app.sap import login_sap

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import sys

def dump_fields(doc_entry=None):
    session_id = login_sap()
    if not session_id:
        print("Falha na autenticação.")
        return

    load_dotenv()
    sap_url = os.getenv('SAP_URL')
    
    cookies = {"B1SESSION": session_id}
    
    # 1. Pega 1 Invoice completa
    if doc_entry:
        print(f"Pegando a Invoice (Nota Fiscal) DocEntry {doc_entry}...")
        url_invoice = f"{sap_url.rstrip('/')}/b1s/v1/Invoices({doc_entry})"
        res_inv = requests.get(url_invoice, cookies=cookies, verify=False)
    else:
        print("Pegando a primeira Invoice (Nota Fiscal) encontrata...")
        url_invoice = f"{sap_url.rstrip('/')}/b1s/v1/Invoices"
        res_inv = requests.get(url_invoice, cookies=cookies, params={"$top": 1, "$filter": "DocumentStatus eq 'bost_Open'"}, verify=False)
    
    invoice_data = {}
    card_code = None
    if res_inv.status_code == 200:
        data = res_inv.json()
        invoice_data = data if not doc_entry else data
        if not doc_entry and "value" in data and data["value"]:
            invoice_data = data["value"][0]
            
        card_code = invoice_data.get("CardCode")
    else:
        print(f"Erro ao buscar nota: {res_inv.status_code} - {res_inv.text}")
        return
    
    # 2. Pega os dados do Parceiro de Negócios correspondente
    bp_data = {}
    if card_code:
        print(f"Pegando dados do Parceiro de Negócio {card_code}...")
        url_bp = f"{sap_url.rstrip('/')}/b1s/v1/BusinessPartners('{card_code}')"
        res_bp = requests.get(url_bp, cookies=cookies, verify=False)
        if res_bp.status_code == 200:
            bp_data = res_bp.json()

    # Salva no arquivo
    dump = {
        "Exemplo_Invoice_Completa": invoice_data,
        "Exemplo_ParceiroDeNegocios_Completo": bp_data
    }
    
    with open("dumps/sap_fields_dump.json", "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=4, ensure_ascii=False)
        
    print("Dump concluído! Verifique o arquivo 'dumps/sap_fields_dump.json' para ver todos os campos disponíveis.")

if __name__ == "__main__":
    entry = sys.argv[1] if len(sys.argv) > 1 else None
    dump_fields(entry)
