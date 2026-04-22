import requests
import urllib3
from .config import get_sap_url, get_sap_auth_payload

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def login_sap():
    payload = get_sap_auth_payload()
    if not all(payload.values()):
        print("Erro: verifique COMPANY_DB, USERNAME, PASSWORD e SAP_URL no .env")
        return None

    login_endpoint = f"{get_sap_url()}/b1s/v1/Login"
    print(f"Tentando logar no SAP em: {login_endpoint}")

    try:
        response = requests.post(login_endpoint, json=payload, verify=False)
        if response.status_code == 200:
            data = response.json()
            print("✅ Login realizado com sucesso!")
            return data.get("SessionId")

        print("❌ Falha no login!")
        print(f"Status Code: {response.status_code}")
        print(f"Detalhes: {response.text}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"❌ Erro de conexão: {e}")
        return None


def _build_url(path: str):
    return f"{get_sap_url()}/{path.lstrip('/') }"


def get_nome_fantasia(session_id: str, card_code: str):
    if not card_code:
        return "N/A"

    endpoint = _build_url(f"b1s/v1/BusinessPartners('{card_code}')")
    try:
        res = requests.get(endpoint, cookies={"B1SESSION": session_id}, params={"$select": "CardForeignName"}, verify=False)
        if res.status_code == 200:
            return res.json().get("CardForeignName") or "N/A"
    except requests.exceptions.RequestException:
        pass

    return "N/A"


def get_account_name(session_id: str, account_code: str):
    if not account_code or account_code == "N/A":
        return "N/A"

    endpoint = _build_url(f"b1s/v1/ChartOfAccounts('{account_code}')")
    try:
        res = requests.get(endpoint, cookies={"B1SESSION": session_id}, params={"$select": "Name"}, verify=False)
        if res.status_code == 200:
            return res.json().get("Name") or "N/A"
    except requests.exceptions.RequestException:
        pass

    return "N/A"


def get_invoice_info(session_id: str, doc_entry: int):
    endpoint = _build_url(f"b1s/v1/Invoices({doc_entry})")
    try:
        res = requests.get(
            endpoint,
            cookies={"B1SESSION": session_id},
            params={"$select": "DocNum,SequenceSerial,U_TX_NDfe,TaxExtension,VATRegNum,DocDate,DocDueDate,DocTotal,CardCode,CardName"},
            verify=False,
        )
        if res.status_code == 200:
            data = res.json()
            tax_ext = data.get("TaxExtension", {})
            cnpj_cpf = tax_ext.get("TaxId0") or tax_ext.get("TaxId4") or data.get("VATRegNum") or "N/A"
            return {
                "doc_num": data.get("DocNum"),
                "numero": data.get("SequenceSerial") or "S/N",
                "nfse": data.get("U_TX_NDfe") or "S/N",
                "cnpj_cpf": cnpj_cpf,
                "doc_date": data.get("DocDate"),
                "due_date": data.get("DocDueDate"),
                "doc_total": data.get("DocTotal"),
                "card_code": data.get("CardCode"),
                "card_name": data.get("CardName"),
            }
    except requests.exceptions.RequestException:
        pass

    return None
