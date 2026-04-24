import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from api import app

client = TestClient(app)

@patch('api.get_db')
def test_list_usuarios(mock_get_db):
    # Mock do cursor e retorno do banco
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    mock_cursor.fetchall.return_value = [{"username": "admin"}, {"username": "zeus"}]
    
    response = client.get("/api/usuarios")
    
    assert response.status_code == 200
    assert response.json() == ["admin", "zeus"]
    mock_cursor.execute.assert_called_with("SELECT username FROM usuarios ORDER BY username ASC")

@patch('api.get_db')
def test_list_contas_razao(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    mock_cursor.fetchall.return_value = [
        {"conta_razao_codigo": "101", "conta_razao_nome": "Banco Brasil"},
        {"conta_razao_codigo": "102", "conta_razao_nome": "Itaú"}
    ]
    
    response = client.get("/api/contas-razao")
    
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["conta_razao_nome"] == "Banco Brasil"

def test_login_invalido():
    with patch('api.get_db') as mock_get_db:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        
        response = client.post("/api/login", json={"username": "wrong", "password": "wrong"})
        assert response.status_code == 401
        assert "Usuário ou senha inválidos" in response.json()["detail"]
