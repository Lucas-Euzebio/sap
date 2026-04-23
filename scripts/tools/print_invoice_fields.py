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

import sys

def dump_fields(doc_entry=None, doc_num=None):
    session_id = login_sap()
    if not session_id:
        print("Falha na autenticação.")
        return

    load_dotenv()
    sap_url = os.getenv('SAP_URL')
    cookies = {"B1SESSION": session_id}
    
    url_base = f"{sap_url.rstrip('/')}/b1s/v1/Invoices"
    
    if doc_entry:
        print(f"🔍 Buscando Invoice pelo DocEntry: {doc_entry}...")
        url = f"{url_base}({doc_entry})"
        res_inv = requests.get(url, cookies=cookies, verify=False)
    elif doc_num:
        print(f"🔍 Buscando Invoice pelo DocNum (SAP): {doc_num}...")
        res_inv = requests.get(url_base, cookies=cookies, params={"$filter": f"DocNum eq {doc_num}"}, verify=False)
    else:
        print("🔍 Buscando a última Invoice em aberto...")
        res_inv = requests.get(url_base, cookies=cookies, params={"$top": 1, "$filter": "DocumentStatus eq 'bost_Open'", "$orderby": "DocNum desc"}, verify=False)
    
    invoice_data = {}
    if res_inv.status_code == 200:
        data = res_inv.json()
        if "value" in data:
            if not data["value"]:
                print("⚠️  Nenhuma nota encontrada com esse critério.")
                return
            invoice_data = data["value"][0]
        else:
            invoice_data = data
    else:
        print(f"❌ Erro ao buscar nota: {res_inv.status_code} - {res_inv.text}")
        return
    
    card_code = invoice_data.get("CardCode")
    bp_data = {}
    if card_code:
        print(f"👤 Buscando dados do Parceiro: {card_code}...")
        url_bp = f"{sap_url.rstrip('/')}/b1s/v1/BusinessPartners('{card_code}')"
        res_bp = requests.get(url_bp, cookies=cookies, verify=False)
        if res_bp.status_code == 200:
            bp_data = res_bp.json()

    # Salva no arquivo
    dump = {
        "Exemplo_Invoice_Completa": invoice_data,
        "Exemplo_ParceiroDeNegocios_Completo": bp_data
    }
    
    output_path = "dumps/sap_fields_dump.json"
    os.makedirs("dumps", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=4, ensure_ascii=False)
        
    print(f"✅ Dump concluído! Verifique em: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspeciona campos brutos de uma Invoice no SAP")
    parser.add_argument("--doc-entry", type=int, help="Filtrar pelo DocEntry (ID interno)")
    parser.add_argument("--doc-num", type=int, help="Filtrar pelo DocNum (Interno SAP)")
    parser.add_argument("--num", type=int, help="Filtrar pelo Número que aparece na tela (SequenceSerial)")
    
    args = parser.parse_args()
    
    # Se usar o --num, vamos adaptar a chamada
    if args.num:
        session_id = login_sap()
        if not session_id:
            print("Falha na autenticação.")
            sys.exit(1)
        load_dotenv()
        sap_url = os.getenv('SAP_URL')
        cookies = {"B1SESSION": session_id}
        url_base = f"{sap_url.rstrip('/')}/b1s/v1/Invoices"
        
        print(f"🔍 Buscando Invoice pelo Número (SequenceSerial): {args.num}...")
        res_inv = requests.get(url_base, cookies=cookies, params={"$filter": f"SequenceSerial eq {args.num}"}, verify=False)
        
        if res_inv.status_code == 200 and res_inv.json().get("value"):
            invoice_data = res_inv.json()["value"][0]
            # Chama a lógica de dump passando o dado já obtido (simulando a função)
            # Para simplificar, vou apenas ajustar o dump_fields para aceitar sequence_serial
            dump_fields(doc_entry=invoice_data["DocEntry"])
        else:
            print(f"❌ Nota {args.num} não encontrada via SequenceSerial.")
    else:
        dump_fields(doc_entry=args.doc_entry, doc_num=args.doc_num)
