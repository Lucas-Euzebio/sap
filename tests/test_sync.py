import pytest
from unittest.mock import patch, MagicMock
from app.sync import sync_recebidas
from datetime import datetime, timedelta

@patch('app.sync.login_sap')
@patch('app.sync.requests.get')
@patch('app.sync.get_db_connection')
def test_sync_recebidas_window(mock_db, mock_get, mock_login):
    # Mock do SAP Login
    mock_login.return_value = "fake_session_123"
    
    # Mock do DB
    mock_conn = MagicMock()
    mock_db.return_value = mock_conn
    
    # Mock do Response do SAP (vazio para simplificar)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"value": []}
    mock_get.return_value = mock_resp
    
    # Executa com uma since_date (ex: hoje)
    today_str = datetime.now().strftime('%Y-%m-%d')
    sync_recebidas(since_date=today_str)
    
    # Verifica se o filtro enviado ao SAP incluiu a janela de 30 dias retroativos
    # safe_date deve ser hoje - 30 dias
    safe_date_dt = datetime.now() - timedelta(days=30)
    safe_date_str = safe_date_dt.strftime('%Y-%m-%d')
    
    # Captura a URL/Parâmetros chamados
    args, kwargs = mock_get.call_args
    params = kwargs.get('params', {})
    filters = params.get('$filter', '')
    
    assert f"DocDate ge '{safe_date_str}'" in filters
    assert "Cancelled eq 'tNO'" in filters
