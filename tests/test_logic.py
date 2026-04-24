import pytest
import datetime
from api import get_date_cond, build_filters

def test_get_date_cond_periodo():
    # Teste para período específico
    cond, params = get_date_cond("data_vencimento", "periodo", "2024-01-01", "2024-01-31")
    assert "data_vencimento >= %s" in cond
    assert "data_vencimento <= %s" in cond
    assert params == ["2024-01-01", "2024-01-31"]

def test_get_date_cond_vazio():
    # Teste sem tipo de data
    cond, params = get_date_cond("data_vencimento", None, None, None)
    assert cond is None
    assert params == []

def test_get_date_cond_este_mes():
    # Teste para atalhos de data (ex: este_mes)
    cond, params = get_date_cond("data_vencimento", "este_mes", None, None)
    assert "data_vencimento >= date_trunc('month', CURRENT_DATE)" in cond
    assert params == []

def test_build_filters_cliente():
    # Teste da construção de filtros por cliente/NFSe
    clauses, params = build_filters(cliente="1423")
    assert any("card_name ILIKE %s" in c for c in clauses)
    assert any("nfse ILIKE %s" in c for c in clauses)
    assert "%1423%" in params

def test_build_filters_responsavel_sem():
    # Teste do filtro especial "Sem Responsável"
    clauses, params = build_filters(responsavel="sem_responsavel")
    assert "(responsavel IS NULL OR responsavel = '')" in clauses
    assert params == []
