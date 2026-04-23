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

# Importa a função de login SAP
from app.sap import login_sap

# Ignorar avisos de segurança sobre certificados
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Cache para o Nome Fantasia dos clientes
bp_cache = {}

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

def format_date(date_str):
    if not date_str:
        return "N/A"
    try:
        date_obj = datetime.strptime(date_str.split("T")[0], "%Y-%m-%d")
        return date_obj.strftime("%d/%m/%Y")
    except:
        return date_str

def get_contas_receber(nfse=None, doc_date=None, due_date=None, card_name=None, doc_entry=None):
    session_id = login_sap()
    
    if not session_id:
        print("Não foi possível autenticar. Cancelando a busca das contas a receber.")
        return

    load_dotenv()
    sap_url = os.getenv('SAP_URL')
    endpoint = f"{sap_url.rstrip('/')}/b1s/v1/Invoices"
    cookies = {"B1SESSION": session_id}
    
    # Montagem dinâmica do filtro
    # Sempre filtra notas em aberto (bost_Open)
    filters = ["DocumentStatus eq 'bost_Open'"]
    
    if doc_entry:
        filters.append(f"DocEntry eq {doc_entry}")
    if nfse:
        filters.append(f"U_TX_NDfe eq '{nfse}'")
    if doc_date: # O OData requer no formato yyyy-mm-dd
        filters.append(f"DocDate eq '{doc_date}'")
    if due_date: # O OData requer no formato yyyy-mm-dd
        filters.append(f"DocDueDate eq '{due_date}'")
    if card_name:
        # Usa contains para buscas parciais de nome de cliente
        filters.append(f"contains(CardName, '{card_name}')")

    final_filter = " and ".join(filters)
    
    print(f"\n🔄 Buscando Notas no endpoint: {endpoint}")
    print(f"Filtro Aplicado: {final_filter} ...\n")
    
    try:
        params = {
            "$filter": final_filter,
            "$orderby": "DocNum desc",
            "$select": "DocNum,DocEntry,CardCode,CardName,DocDate,DocDueDate,DocTotal,PaidToDate,WTApplied,WTAmount,SequenceSerial,VATRegNum,TaxExtension,DocumentInstallments,DocumentLines,U_TX_NDfe"
        }
        
        headers = {
            "Prefer": "odata.maxpagesize=20"
        }
        
        response = requests.get(endpoint, cookies=cookies, headers=headers, params=params, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            contas = data.get("value", [])
            
            print(f"✅ Total de Contas a Receber retornadas nesta página: {len(contas)}\n")
            
            for conta in contas:
                doc_entry_val = conta.get("DocEntry")
                doc_num = conta.get("DocNum")
                numero_documento = conta.get("SequenceSerial") or "S/N"
                nfse_valor = conta.get("U_TX_NDfe") or "S/N"
                
                card_code = conta.get("CardCode")
                card_name_res = conta.get("CardName")
                
                tax_ext = conta.get("TaxExtension", {})
                cnpj_cpf = tax_ext.get("TaxId0") or tax_ext.get("TaxId4")
                if not cnpj_cpf:
                    cnpj_cpf = "N/A"
                
                doc_date_str = conta.get("DocDate", "")
                doc_due_date_str = conta.get("DocDueDate", "")
                
                doc_date_formatted = format_date(doc_date_str)
                doc_due_date_formatted = format_date(doc_due_date_str)
                
                doc_total = float(conta.get("DocTotal", 0.0))
                paid_to_date = float(conta.get("PaidToDate", 0.0))
                wt_applied = float(conta.get("WTApplied", 0.0))
                wt_amount = float(conta.get("WTAmount", 0.0))

                if wt_applied > 0:
                    # Nota já paga: cliente reteve CSLL+PIS+COFINS+IRRF
                    retem = wt_applied
                elif wt_amount > 0:
                    # Nota não paga: estima retenção CSLL(1%)+PIS(0,65%)+COFINS(3%)=4,65% do LineTotal
                    line_total = sum(float(l.get("LineTotal", 0.0)) for l in conta.get("DocumentLines", []))
                    retem = line_total * 0.0465
                else:
                    retem = 0.0

                valor_liquido = doc_total - retem
                saldo_documento = valor_liquido - paid_to_date
                
                nome_fantasia = get_nome_fantasia(sap_url, session_id, card_code)
                
                print(f"==================================================")
                print(f"📄 DocEntry SAP: {doc_entry_val} | DocNum: {doc_num} | NFS-e: {nfse_valor}")
                print(f"🔢 Número do Documento: {numero_documento}")
                print(f"🔢 Código do Cliente: {card_code}")
                print(f"👤 Nome do Cliente: {card_name_res}")
                print(f"🏢 Nome Fantasia: {nome_fantasia} | CNPJ/CPF: {cnpj_cpf}")
                print(f"📅 Data Documento: {doc_date_formatted} | Vencimento Geral: {doc_due_date_formatted}")
                
                installments = conta.get("DocumentInstallments", [])
                if installments:
                    print("💰 Parcelas / Saldo:")
                    for inst in installments:
                        inst_vencimento = format_date(inst.get("DueDate", ""))
                        inst_total = inst.get("Total", 0.0)
                        
                        inst_pagamento = inst.get("U_TX_dPag")
                        inst_pagamento_str = format_date(inst_pagamento) if inst_pagamento else "Pendente"
                        
                        print(f"   -> Parcela {inst.get('InstallmentId')}: Vence {inst_vencimento} | Valor Parcela: R$ {inst_total:.2f} | Paga em: {inst_pagamento_str}")
                
                print(f"💵 Total Bruto: R$ {doc_total:.2f} | Retenção (CSLL+PIS+COFINS): R$ {retem:.2f} | Valor Líquido: R$ {valor_liquido:.2f}")
                print(f"💰 Saldo Pendente (Líquido): R$ {saldo_documento:.2f}")
                print(f"==================================================\n")
                
        else:
            print(f"\n❌ Falha ao buscar contas a receber: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"\n❌ Erro durante a requisição: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consulta Contas a Receber no SAP Business One")
    parser.add_argument("--nfse", type=str, help="Filtrar por número da NFS-e (U_TX_NDfe)")
    parser.add_argument("--doc-entry", type=str, help="Filtrar pelo ID interno DocEntry do SAP")
    parser.add_argument("--doc-date", type=str, help="Filtrar por Data do Documento no formato YYYY-MM-DD")
    parser.add_argument("--due-date", type=str, help="Filtrar por Data de Vencimento no formato YYYY-MM-DD")
    parser.add_argument("--card-name", type=str, help="Filtrar pelo Nome do Cliente (CardName)")
    
    args = parser.parse_args()
    
    get_contas_receber(
        nfse=args.nfse,
        doc_entry=args.doc_entry,
        doc_date=args.doc_date,
        due_date=args.due_date,
        card_name=args.card_name
    )
