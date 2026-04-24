import pytest
from unittest.mock import patch, MagicMock
from app.outlook import fetch_nfse_pdf
import os
import base64

@patch('app.outlook.requests.get')
@patch('app.outlook.requests.post')
def test_fetch_nfse_pdf_success(mock_post, mock_get):
    # Mock do token response
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "fake_token_123"}
    mock_post.return_value = mock_token_resp
    
    # Mock do Graph API Email response
    pdf_content = b'%PDF-1.4 Fake PDF file coming from tests'
    pdf_b64 = base64.b64encode(pdf_content).decode('utf-8')
    
    fake_messages = {
        "value": [
            {
                "id": "AAMk...",
                "subject": "Nota Fiscal 5555",
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": "nfse_xml.xml",
                        "contentBytes": "base64_xml"
                    },
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": "NFe_5555.pdf",
                        "contentBytes": pdf_b64
                    }
                ]
            }
        ]
    }
    
    mock_msg_resp = MagicMock()
    mock_msg_resp.status_code = 200
    mock_msg_resp.json.return_value = fake_messages
    mock_get.return_value = mock_msg_resp
    
    env_vars = {
        "AZURE_TENANT_ID": "123",
        "AZURE_CLIENT_ID": "abc",
        "AZURE_CLIENT_SECRET": "xyz",
        "AZURE_USER_MAILBOX": "faturamento@empresa.com.br"
    }
    
    with patch.dict(os.environ, env_vars):
        result = fetch_nfse_pdf("5555")
        
    assert result is not None
    assert result.endswith("nfse_5555.pdf")
    assert os.path.exists(result)
    
    # Cleanup do arquivo fake gerado
    os.remove(result)

@patch('app.outlook.requests.get')
@patch('app.outlook.requests.post')
def test_fetch_nfse_pdf_no_email_found(mock_post, mock_get):
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "fake_token_123"}
    mock_post.return_value = mock_token_resp
    
    # Retorna uma lista vazia de mensagens
    mock_msg_resp = MagicMock()
    mock_msg_resp.status_code = 200
    mock_msg_resp.json.return_value = {"value": []}
    mock_get.return_value = mock_msg_resp
    
    env_vars = {
        "AZURE_TENANT_ID": "123",
        "AZURE_CLIENT_ID": "abc",
        "AZURE_CLIENT_SECRET": "xyz",
        "AZURE_USER_MAILBOX": "faturamento@empresa.com.br"
    }
    
    with patch.dict(os.environ, env_vars):
        result = fetch_nfse_pdf("9999")
        
    assert result is None
