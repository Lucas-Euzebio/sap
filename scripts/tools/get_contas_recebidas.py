import os
import sys
from pathlib import Path
import requests
import argparse
from dotenv import load_dotenv
from datetime import datetime

# Adiciona a raiz do projeto ao sys.path para permitir imports do módulo 'app'
root_path = str(Path(__file__).resolve().parent.parent.parent)
if root_path not in sys.path:
    sys.path.append(root_path)

from app.sap import login_sap
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

bp_cache = {}
invoice_cache = {}
account_cache = {}

def get_nome_fantasia(sap_url, session_id, card_code):
    if card_code in bp_cache:
        return bp_cache[card_code]
    
    endpoint = f"{sap_url.rstrip('/')}/b1s/v1/BusinessPartners('{card_code}')"
    try:
        res = requests.get(
            endpoint, 
            cookies={"B1SESSION": session_id}, 
            params={"$select": "CardForeignName"}, 
            verify=False
        )
        if res.status_code == 200:
            foreign_name = res.json().get("CardForeignName")
            bp_cache[card_code] = foreign_name if foreign_name else "N/A"
            return bp_cache[card_code]
    except:
        pass
    
    bp_cache[card_code] = "N/A"
    return "N/A"

def get_account_name(sap_url, session_id, account_code):
    if not account_code or account_code == "N/A":
        return "N/A"
    if account_code in account_cache:
        return account_cache[account_code]
        
    endpoint = f"{sap_url.rstrip('/')}/b1s/v1/ChartOfAccounts('{account_code}')"
    try:
        res = requests.get(
            endpoint, 
            cookies={"B1SESSION": session_id}, 
            params={"$select": "Name"}, 
            verify=False
        )
        if res.status_code == 200:
            name = res.json().get("Name")
            account_cache[account_code] = name if name else "N/A"
            return account_cache[account_code]
    except:
        pass
        
    account_cache[account_code] = "N/A"
    return "N/A"

def get_invoice_info(sap_url, session_id, doc_entry):
    """Busca o SequenceSerial (Número) e U_TX_NDfe (NFS-e) da Invoice associada ao Pagamento."""
    if doc_entry in invoice_cache:
        return invoice_cache[doc_entry]
        
    endpoint = f"{sap_url.rstrip('/')}/b1s/v1/Invoices({doc_entry})"
    try:
        res = requests.get(
            endpoint, 
            cookies={"B1SESSION": session_id}, 
            params={"$select": "SequenceSerial,U_TX_NDfe,TaxExtension,VATRegNum,DocDate,DocDueDate"}, 
            verify=False
        )
        if res.status_code == 200:
            data = res.json()
            
            tax_ext = data.get("TaxExtension", {})
            cnpj_cpf = tax_ext.get("TaxId0") or tax_ext.get("TaxId4")
            if not cnpj_cpf:
                cnpj_cpf = data.get("VATRegNum", "N/A")
                
            info = {
                "numero": data.get("SequenceSerial") or "S/N",
                "nfse": data.get("U_TX_NDfe") or "S/N",
                "cnpj_cpf": cnpj_cpf,
                "doc_date": data.get("DocDate"),
                "due_date": data.get("DocDueDate")
            }
            invoice_cache[doc_entry] = info
            return info
    except:
        pass
        
    return {"numero": "S/N", "nfse": "S/N", "cnpj_cpf": "N/A", "doc_date": None, "due_date": None}

def format_date(date_str):
    if not date_str:
        return "N/A"
    try:
        date_obj = datetime.strptime(date_str.split("T")[0], "%Y-%m-%d")
        return date_obj.strftime("%d/%m/%Y")
    except:
        return date_str

def get_contas_recebidas(doc_date=None, card_name=None):
    session_id = login_sap()
    
    if not session_id:
        print("Não foi possível autenticar.")
        return

    load_dotenv()
    sap_url = os.getenv('SAP_URL')
    
    # Endpoint de Contas Recebidas reais (Contas a Receber / Incoming Payments)
    endpoint = f"{sap_url.rstrip('/')}/b1s/v1/IncomingPayments"
    cookies = {"B1SESSION": session_id}
    
    # Filtro focado em trazer apenas os pagamentos confirmados (NÃO Cancelados)
    filters = ["Cancelled eq 'tNO'"]
    
    if doc_date:
        filters.append(f"DocDate eq '{doc_date}'")
    if card_name:
        filters.append(f"contains(CardName, '{card_name}')")

    final_filter = " and ".join(filters)
    
    print(f"\n🔄 Buscando Pagamentos Recebidos no endpoint: {endpoint}")
    print(f"Filtro Aplicado: {final_filter} ...\n")
    
    try:
        params = {
            "$filter": final_filter,
            "$orderby": "DocNum desc"
        }
        
        headers = {
            "Prefer": "odata.maxpagesize=20"
        }
        
        response = requests.get(endpoint, cookies=cookies, headers=headers, params=params, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            pagamentos = data.get("value", [])
            
            print(f"✅ Total de Registros de Recebimento encontrados: {len(pagamentos)}\n")
            
            for pg in pagamentos:
                doc_num_pagamento = pg.get("DocNum")
                card_code = pg.get("CardCode")
                card_name_res = pg.get("CardName")
                
                # A Data do pagamento é o DocDate do IncomingPayments
                data_pagamento = format_date(pg.get("DocDate", ""))
                
                # Determina qual foi a conta contábil/bancária (Razão) que recebeu o dinheiro
                conta_razao_code = None
                if pg.get("TransferSum", 0) > 0:
                    conta_razao_code = pg.get("TransferAccount")
                elif pg.get("CashSum", 0) > 0:
                    conta_razao_code = pg.get("CashAccount")
                elif pg.get("CheckAccount"):
                    # Caso tenha sido cheque e tenha conta, mas não é garantia
                    conta_razao_code = pg.get("CheckAccount")
                elif pg.get("BoeAccount"): # Boleto
                    conta_razao_code = pg.get("BoeAccount")
                    
                if not conta_razao_code:
                    conta_razao_code = "N/A"
                    
                conta_razao_nome = get_account_name(sap_url, session_id, conta_razao_code)
                
                # O total pago pode estar segmentado em Cash/Transfer, mas 'DocTotal' existe em algumas localizações,
                # se DocTotal for Null (igual ocorre no B1 as vezes pra pagamentos), somamos os fields.
                total_pago = pg.get("DocTotal")
                if total_pago is None:
                    # Em IncomingPayments, o Total real pago seria a soma das formas de pagamento
                    total_pago = pg.get("CashSum", 0.0) + pg.get("TransferSum", 0.0)
                    # Caso tenhamos que lidar com mais pagamentos, adicionaríamos CheckSum, BoeSum, etc.
                
                nome_fantasia = get_nome_fantasia(sap_url, session_id, card_code)
                
                print(f"==================================================")
                print(f"🟢 RECEBIMENTO Nº SAP: {doc_num_pagamento} | Data do Pagamento: {data_pagamento}")
                print(f"👤 Cliente: {card_code} - {card_name_res}")
                print(f"🏢 Nome Fantasia: {nome_fantasia}")
                print(f"🏦 Conta do Razão: {conta_razao_code} - {conta_razao_nome}")
                print(f"💵 Total Recebido Neste Documento: R$ {total_pago:.2f}")
                
                # Verifica quais faturas (NFS-e) este pagamento baixou
                invoices_pagas = pg.get("PaymentInvoices", [])
                if invoices_pagas:
                    print(f"🔗 Notas Fiscais Baixadas por este Pagamento:")
                    for inv in invoices_pagas:
                        # Se for do tipo Fatura de saída normal
                        if inv.get("InvoiceType") == "it_Invoice":
                            doc_entry_inv = inv.get("DocEntry")
                            valor_aplicado = inv.get("SumApplied", 0.0)
                            
                            # Busca as informações da NFS-e dinamicamente
                            info_nfe = get_invoice_info(sap_url, session_id, doc_entry_inv)
                            doc_date_nf = format_date(info_nfe.get("doc_date"))
                            due_date_nf = format_date(info_nfe.get("due_date"))
                            
                            print(f"   -> NFS-e: {info_nfe['nfse']} | Num.Doc: {info_nfe['numero']} | CNPJ/CPF: {info_nfe['cnpj_cpf']} | Emissão: {doc_date_nf} | Venc.: {due_date_nf} | Valor Baixado: R$ {valor_aplicado:.2f}")
                
                print(f"==================================================\n")
                
        else:
            print(f"\n❌ Falha ao buscar pagamentos recebidos: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"\n❌ Erro durante a requisição: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consulta Contas Recebidas no SAP Business One")
    parser.add_argument("--doc-date", type=str, help="Filtrar por Data do Pagamento no formato YYYY-MM-DD")
    parser.add_argument("--card-name", type=str, help="Filtrar pelo Nome do Cliente (CardName)")
    
    args = parser.parse_args()
    
    get_contas_recebidas(
        doc_date=args.doc_date,
        card_name=args.card_name
    )
