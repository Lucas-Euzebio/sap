import os
import requests
import base64

def fetch_nfse_pdf(nfse_number: str) -> str:
    """
    Busca um e-mail no Outlook usando Microsoft Graph API, encontra
    anexos em PDF relacionados e salva no disco.
    """
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    mailbox = os.getenv("AZURE_USER_MAILBOX") # O e-mail da conta compartilhada

    if not all([tenant_id, client_id, client_secret, mailbox]):
        print("Configuração do Azure Auth / Graph API ausente no .env.")
        return None

    try:
        # 1. Obter Access Token usando Client Credentials Flow
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = {
            "client_id": client_id,
            "scope": "https://graph.microsoft.com/.default",
            "client_secret": client_secret,
            "grant_type": "client_credentials"
        }
        
        token_r = requests.post(token_url, data=token_data)
        if token_r.status_code != 200:
            print("Erro ao obter token do Azure:", token_r.text)
            return None
            
        access_token = token_r.json().get("access_token")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        
        # 2. Buscar E-mail (via search que pesquisa texto/assunto)
        search_query = f'"{nfse_number}"'
        graph_url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages?$search={search_query}&$expand=attachments"
        
        msg_r = requests.get(graph_url, headers=headers)
        if msg_r.status_code != 200:
            print("Erro ao buscar e-mail no Graph API:", msg_r.text)
            return None
            
        messages = msg_r.json().get("value", [])
        if not messages:
            print(f"Nenhum e-mail encontrado para NFSe {nfse_number}.")
            return None
            
        # 3. Baixar Anexo PDF (se encontrar)
        for msg in messages:
            attachments = msg.get("attachments", [])
            for att in attachments:
                name = att.get("name", "").lower()
                # O Graph API retorna anexos do tipo fileAttachment em base64 bytes string
                if name.endswith(".pdf") and "fileattachment" in str(att.get("@odata.type", "")).lower():
                    content_b64 = att.get("contentBytes")
                    if content_b64:
                        pdf_bytes = base64.b64decode(content_b64)
                        
                        save_dir = "static/anexos"
                        os.makedirs(save_dir, exist_ok=True)
                        filepath = os.path.join(save_dir, f"nfse_{nfse_number}.pdf")
                        
                        with open(filepath, 'wb') as f:
                            f.write(pdf_bytes)
                            
                        return filepath
        return None
        
    except Exception as e:
        print(f"Erro inesperado na integração com Outlook/Graph: {e}")
        return None
