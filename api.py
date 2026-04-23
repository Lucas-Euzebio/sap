import os
import datetime
import jwt
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from app.db import get_db_connection
from app.sync import sync_invoices, sync_recebidas

# Configuração JWT
SECRET_KEY = "zeus_agro_secret_key"
ALGORITHM = "HS256"

app = FastAPI(title="Zeus Agrotech - Cobranças")

def get_db():
    return get_db_connection()

# Models
class HistoricoCreate(BaseModel):
    responsavel: str
    acao: str
    observacao: str
    data_promessa: Optional[str] = None

class ObservacaoCliente(BaseModel):
    observacao: str
    atualizado_por: Optional[str] = None

class NotaUpdate(BaseModel):
    nfse: Optional[str] = None
    data_emissao: Optional[str] = None
    data_vencimento: Optional[str] = None
    conta_razao_codigo: Optional[str] = None
    conta_razao_nome: Optional[str] = None
    banco: Optional[str] = None
    valor_total: Optional[float] = None
    saldo_pendente: Optional[float] = None
    status_cobranca: Optional[str] = None
    responsavel: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

def get_date_cond(col_name, type_val, start, end):
    if not type_val: return None, []
    p = []
    cond = ""
    if type_val == "semana_passada":
        cond = f"{col_name} >= date_trunc('week', CURRENT_DATE - INTERVAL '1 week') AND {col_name} < date_trunc('week', CURRENT_DATE)"
    elif type_val == "esta_semana":
        cond = f"{col_name} >= date_trunc('week', CURRENT_DATE) AND {col_name} < date_trunc('week', CURRENT_DATE + INTERVAL '1 week')"
    elif type_val == "proxima_semana":
        cond = f"{col_name} >= date_trunc('week', CURRENT_DATE + INTERVAL '1 week') AND {col_name} < date_trunc('week', CURRENT_DATE + INTERVAL '2 weeks')"
    elif type_val == "mes_passado":
        cond = f"{col_name} >= date_trunc('month', CURRENT_DATE - INTERVAL '1 month') AND {col_name} < date_trunc('month', CURRENT_DATE)"
    elif type_val == "este_mes":
        cond = f"{col_name} >= date_trunc('month', CURRENT_DATE) AND {col_name} < date_trunc('month', CURRENT_DATE + INTERVAL '1 month')"
    elif type_val == "proximo_mes":
        cond = f"{col_name} >= date_trunc('month', CURRENT_DATE + INTERVAL '1 month') AND {col_name} < date_trunc('month', CURRENT_DATE + INTERVAL '2 months')"
    elif type_val == "ano_passado":
        cond = f"{col_name} >= date_trunc('year', CURRENT_DATE - INTERVAL '1 year') AND {col_name} < date_trunc('year', CURRENT_DATE)"
    elif type_val == "este_ano":
        cond = f"{col_name} >= date_trunc('year', CURRENT_DATE) AND {col_name} < date_trunc('year', CURRENT_DATE + INTERVAL '1 year')"
    elif type_val == "proximo_ano":
        cond = f"{col_name} >= date_trunc('year', CURRENT_DATE + INTERVAL '1 year') AND {col_name} < date_trunc('year', CURRENT_DATE + INTERVAL '2 years')"
    elif type_val == "periodo" and (start or end):
        cs = []
        if start:
            cs.append(f"{col_name} >= %s")
            p.append(start)
        if end:
            cs.append(f"{col_name} <= %s")
            p.append(end)
        if cs:
            cond = " AND ".join(cs)
    return cond or None, p

def build_filters(vencimento=None, vencimento_inicio=None, vencimento_fim=None, cliente=None, responsavel=None, pagamento=None, pagamento_inicio=None, pagamento_fim=None, emissao=None, emissao_inicio=None, emissao_fim=None):
    clauses = ["1=1"]
    params = []
    
    if cliente:
        clauses.append("(card_name ILIKE %s OR card_code ILIKE %s OR nfse ILIKE %s OR numero_documento ILIKE %s)")
        params.extend([f"%{cliente}%", f"%{cliente}%", f"%{cliente}%", f"%{cliente}%"])
    if responsavel:
        if responsavel == "sem_responsavel":
            clauses.append("(responsavel IS NULL OR responsavel = '')")
        else:
            clauses.append("responsavel ILIKE %s")
            params.append(f"%{responsavel}%")
        
    v_cond, v_params = get_date_cond("data_vencimento", vencimento, vencimento_inicio, vencimento_fim)
    if v_cond:
        clauses.append(f"({v_cond})")
        params.extend(v_params)

    p_cond, p_params = get_date_cond("data_pagamento", pagamento, pagamento_inicio, pagamento_fim)
    if p_cond:
        clauses.append(f"({p_cond})")
        params.extend(p_params)

    e_cond, e_params = get_date_cond("data_emissao", emissao, emissao_inicio, emissao_fim)
    if e_cond:
        clauses.append(f"({e_cond})")
        params.extend(e_params)
        
    return clauses, params


@app.get("/api/dashboard")
def get_dashboard_metrics(
    vencimento: Optional[str] = None,
    vencimento_inicio: Optional[str] = None,
    vencimento_fim: Optional[str] = None,
    cliente: Optional[str] = None,
    responsavel: Optional[str] = None,
    pagamento: Optional[str] = None,
    pagamento_inicio: Optional[str] = None,
    pagamento_fim: Optional[str] = None,
    emissao: Optional[str] = None,
    emissao_inicio: Optional[str] = None,
    emissao_fim: Optional[str] = None
):
    """Retorna KPIs consolidados do painel principal respeitando filtros."""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    shared_clauses, shared_params = build_filters(
        vencimento, vencimento_inicio, vencimento_fim, 
        cliente, responsavel,
        pagamento, pagamento_inicio, pagamento_fim,
        emissao, emissao_inicio, emissao_fim
    )
    where_shared = " AND ".join(shared_clauses)

    # --- KPIs de Contas a Receber (pendentes) ---
    cursor.execute(f"""
        SELECT
            COUNT(*) as total_notas_abertas,
            COUNT(DISTINCT card_code) as total_clientes_abertos,
            COALESCE(SUM(saldo_pendente), 0) as total_a_receber,
            COALESCE(SUM(CASE WHEN data_vencimento < CURRENT_DATE THEN saldo_pendente ELSE 0 END), 0) as total_atrasado,
            COALESCE(SUM(CASE WHEN data_vencimento >= CURRENT_DATE THEN saldo_pendente ELSE 0 END), 0) as total_no_prazo,
            COUNT(CASE WHEN data_vencimento < CURRENT_DATE THEN 1 END) as qtd_notas_atrasadas,
            COUNT(CASE WHEN data_vencimento >= CURRENT_DATE THEN 1 END) as qtd_notas_no_prazo,
            COUNT(CASE WHEN responsavel IS NULL OR responsavel = '' THEN 1 END) as qtd_sem_responsavel,
            COUNT(CASE WHEN responsavel IS NOT NULL AND responsavel != '' THEN 1 END) as qtd_com_responsavel
        FROM notas_cobranca
        WHERE saldo_pendente > 0 AND {where_shared}
    """, shared_params)
    a_receber = cursor.fetchone()

    # --- KPIs de Contas Recebidas ---
    cursor.execute(f"""
        SELECT
            COUNT(*) as total_notas_recebidas,
            COUNT(DISTINCT card_code) as total_clientes_recebidos,
            COALESCE(SUM(valor_total), 0) as total_recebido,
            COALESCE(SUM(CASE WHEN data_pagamento > data_vencimento THEN valor_total ELSE 0 END), 0) as total_recebido_atrasado,
            COALESCE(SUM(CASE WHEN data_pagamento <= data_vencimento THEN valor_total ELSE 0 END), 0) as total_recebido_no_prazo,
            COALESCE(SUM(CASE WHEN EXTRACT(MONTH FROM data_pagamento) = EXTRACT(MONTH FROM CURRENT_DATE)
                               AND EXTRACT(YEAR FROM data_pagamento) = EXTRACT(YEAR FROM CURRENT_DATE)
                          THEN valor_total ELSE 0 END), 0) as recebido_este_mes,
            COUNT(CASE WHEN EXTRACT(MONTH FROM data_pagamento) = EXTRACT(MONTH FROM CURRENT_DATE)
                        AND EXTRACT(YEAR FROM data_pagamento) = EXTRACT(YEAR FROM CURRENT_DATE)
                   THEN 1 END) as qtd_recebida_este_mes,
            COUNT(CASE WHEN responsavel IS NULL OR responsavel = '' THEN 1 END) as qtd_recebidas_sem_responsavel,
            COUNT(CASE WHEN responsavel IS NOT NULL AND responsavel != '' THEN 1 END) as qtd_recebidas_com_responsavel
        FROM notas_cobranca
        WHERE data_pagamento IS NOT NULL AND {where_shared}
    """, shared_params)
    recebidas = cursor.fetchone()

    # --- Por Responsável: A Receber ---
    cursor.execute(f"""
        SELECT
            COALESCE(responsavel, 'Sem Responsável') as responsavel,
            COUNT(*) as qtd_notas,
            COUNT(DISTINCT card_code) as qtd_clientes,
            COALESCE(SUM(saldo_pendente), 0) as total_carteira
        FROM notas_cobranca
        WHERE saldo_pendente > 0 AND {where_shared}
        GROUP BY COALESCE(responsavel, 'Sem Responsável')
        ORDER BY total_carteira DESC
        LIMIT 10
    """, shared_params)
    por_responsavel_receber = cursor.fetchall()

    # --- Por Responsável: Recebidas ---
    cursor.execute(f"""
        SELECT
            COALESCE(responsavel, 'Sem Responsável') as responsavel,
            COUNT(*) as qtd_notas,
            COALESCE(SUM(valor_total), 0) as total_recebido
        FROM notas_cobranca
        WHERE data_pagamento IS NOT NULL AND {where_shared}
        GROUP BY COALESCE(responsavel, 'Sem Responsável')
        ORDER BY total_recebido DESC
        LIMIT 10
    """, shared_params)
    por_responsavel_recebidas = cursor.fetchall()

    # --- Aging: Vencimentos em buckets ---
    cursor.execute(f"""
        SELECT
            COUNT(CASE WHEN data_vencimento >= CURRENT_DATE THEN 1 END) as a_vencer,
            COUNT(CASE WHEN data_vencimento < CURRENT_DATE AND data_vencimento >= CURRENT_DATE - 30 THEN 1 END) as ate_30d,
            COUNT(CASE WHEN data_vencimento < CURRENT_DATE - 30 AND data_vencimento >= CURRENT_DATE - 60 THEN 1 END) as de_31_60d,
            COUNT(CASE WHEN data_vencimento < CURRENT_DATE - 60 AND data_vencimento >= CURRENT_DATE - 90 THEN 1 END) as de_61_90d,
            COUNT(CASE WHEN data_vencimento < CURRENT_DATE - 90 THEN 1 END) as acima_90d,
            COALESCE(SUM(CASE WHEN data_vencimento >= CURRENT_DATE THEN saldo_pendente ELSE 0 END), 0) as val_a_vencer,
            COALESCE(SUM(CASE WHEN data_vencimento < CURRENT_DATE AND data_vencimento >= CURRENT_DATE - 30 THEN saldo_pendente ELSE 0 END), 0) as val_ate_30d,
            COALESCE(SUM(CASE WHEN data_vencimento < CURRENT_DATE - 30 AND data_vencimento >= CURRENT_DATE - 60 THEN saldo_pendente ELSE 0 END), 0) as val_de_31_60d,
            COALESCE(SUM(CASE WHEN data_vencimento < CURRENT_DATE - 60 AND data_vencimento >= CURRENT_DATE - 90 THEN saldo_pendente ELSE 0 END), 0) as val_de_61_90d,
            COALESCE(SUM(CASE WHEN data_vencimento < CURRENT_DATE - 90 THEN saldo_pendente ELSE 0 END), 0) as val_acima_90d
        FROM notas_cobranca
        WHERE saldo_pendente > 0 AND {where_shared}
    """, shared_params)
    aging = cursor.fetchone()

    # --- Top 5 maiores devedores ---
    cursor.execute(f"""
        SELECT card_code, card_name, SUM(saldo_pendente) as total_devendo, COUNT(*) as qtd_notas
        FROM notas_cobranca
        WHERE saldo_pendente > 0 AND {where_shared}
        GROUP BY card_code, card_name
        ORDER BY total_devendo DESC
        LIMIT 5
    """, shared_params)
    top_devedores = cursor.fetchall()

    cursor.close()
    conn.close()

    return {
        "a_receber": a_receber,
        "recebidas": recebidas,
        "por_responsavel_receber": por_responsavel_receber,
        "por_responsavel_recebidas": por_responsavel_recebidas,
        "aging": aging,
        "top_devedores": top_devedores,
    }


@app.get("/api/clientes")
def get_clientes(
    status: Optional[str] = None,
    vencimento: Optional[str] = None,
    vencimento_inicio: Optional[str] = None,
    vencimento_fim: Optional[str] = None,
    cliente: Optional[str] = None,
    responsavel: Optional[str] = None,
    ordenacao: Optional[str] = None,
    pago: bool = False,
    pagamento: Optional[str] = None,
    pagamento_inicio: Optional[str] = None,
    pagamento_fim: Optional[str] = None,
    conta_razao: Optional[str] = None
):
    """Retorna os clientes agrupados pelo total do saldo devedor e contagem de notas, aplicando filtros e ordenação"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    where_clauses = ["1=1"]
    params = [pago, pago, pago]
    
    if pago:
        where_clauses.append("data_pagamento IS NOT NULL")
    else:
        where_clauses.append("saldo_pendente > 0")
    
    if cliente:
        where_clauses.append("(card_name ILIKE %s OR card_code ILIKE %s OR nfse ILIKE %s OR numero_documento ILIKE %s)")
        params.extend([f"%{cliente}%", f"%{cliente}%", f"%{cliente}%", f"%{cliente}%"])
    if responsavel:
        if responsavel == "sem_responsavel":
            where_clauses.append("(responsavel IS NULL OR responsavel = '')")
        else:
            where_clauses.append("responsavel ILIKE %s")
            params.append(f"%{responsavel}%")

    v_cond, v_params = get_date_cond("data_vencimento", vencimento, vencimento_inicio, vencimento_fim)
    if v_cond:
        where_clauses.append(f"({v_cond})")
        params.extend(v_params)

    p_cond, p_params = get_date_cond("data_pagamento", pagamento, pagamento_inicio, pagamento_fim)
    if p_cond:
        where_clauses.append(f"({p_cond})")
        params.extend(p_params)

    if status:
        where_clauses.append("status_cobranca = %s")
        params.append(status)
    if conta_razao:
        where_clauses.append("conta_razao_codigo = %s")
        params.append(conta_razao)

    where_sql = " AND ".join(where_clauses)

    query = f"""
        SELECT card_code, card_name, 
               COUNT(id) as qtd_notas, 
               SUM(CASE WHEN %s THEN valor_total ELSE saldo_pendente END) as saldo_total,
               SUM(CASE 
                    WHEN %s THEN (CASE WHEN data_pagamento > data_vencimento THEN valor_total ELSE 0 END)
                    ELSE (CASE WHEN data_vencimento < CURRENT_DATE THEN saldo_pendente ELSE 0 END)
               END) as saldo_atrasado,
               SUM(CASE 
                    WHEN %s THEN (CASE WHEN data_pagamento <= data_vencimento THEN valor_total ELSE 0 END)
                    ELSE (CASE WHEN data_vencimento >= CURRENT_DATE THEN saldo_pendente ELSE 0 END)
               END) as saldo_no_prazo,
               MIN(data_vencimento) as vencimento_mais_antigo,
               MIN(CASE WHEN data_vencimento < CURRENT_DATE THEN data_vencimento ELSE NULL END) as vencimento_atrasado_mais_antigo,
               MIN(data_promessa) as data_promessa_mais_proxima,
               STRING_AGG(DISTINCT responsavel, ', ') as responsaveis
        FROM notas_cobranca
        WHERE {" AND ".join(where_clauses)}
        GROUP BY card_code, card_name
    """
    
    order_clause = "ORDER BY saldo_total DESC"
    if ordenacao == "menor_saldo":
        order_clause = "ORDER BY saldo_total ASC"
    elif ordenacao == "vencimento_antigo":
        order_clause = "ORDER BY vencimento_mais_antigo ASC NULLS LAST"
    elif ordenacao == "vencimento_novo":
        order_clause = "ORDER BY vencimento_mais_antigo DESC NULLS LAST"
    elif ordenacao == "maior_atraso":
        order_clause = "ORDER BY saldo_atrasado DESC"
    elif ordenacao == "nome_az":
        order_clause = "ORDER BY card_name ASC"
    elif ordenacao == "responsavel":
        order_clause = "ORDER BY responsaveis ASC NULLS LAST"
        
    query += f" {order_clause}"
    
    cursor.execute(query, params)
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return resultados

@app.get("/api/clientes/{card_code}/resumo")
def get_resumo_cliente(
    card_code: str, 
    pago: bool = False,
    vencimento: Optional[str] = None,
    vencimento_inicio: Optional[str] = None,
    vencimento_fim: Optional[str] = None,
    pagamento: Optional[str] = None,
    pagamento_inicio: Optional[str] = None,
    pagamento_fim: Optional[str] = None
):
    """Retorna sumarização financeira filtrada + observação geral do cliente"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    where_clauses = ["card_code = %s"]
    params = [pago, pago, pago, card_code]

    if pago:
        where_clauses.append("data_pagamento IS NOT NULL")
    else:
        where_clauses.append("saldo_pendente > 0")

    def get_date_cond(col_name, type_val, start, end):
        if not type_val: return None, []
        p = []
        cond = ""
        if type_val == "semana_passada":
            cond = f"{col_name} >= date_trunc('week', CURRENT_DATE - INTERVAL '1 week') AND {col_name} < date_trunc('week', CURRENT_DATE)"
        elif type_val == "esta_semana":
            cond = f"{col_name} >= date_trunc('week', CURRENT_DATE) AND {col_name} < date_trunc('week', CURRENT_DATE + INTERVAL '1 week')"
        elif type_val == "proxima_semana":
            cond = f"{col_name} >= date_trunc('week', CURRENT_DATE + INTERVAL '1 week') AND {col_name} < date_trunc('week', CURRENT_DATE + INTERVAL '2 weeks')"
        elif type_val == "mes_passado":
            cond = f"{col_name} >= date_trunc('month', CURRENT_DATE - INTERVAL '1 month') AND {col_name} < date_trunc('month', CURRENT_DATE)"
        elif type_val == "este_mes":
            cond = f"{col_name} >= date_trunc('month', CURRENT_DATE) AND {col_name} < date_trunc('month', CURRENT_DATE + INTERVAL '1 month')"
        elif type_val == "proximo_mes":
            cond = f"{col_name} >= date_trunc('month', CURRENT_DATE + INTERVAL '1 month') AND {col_name} < date_trunc('month', CURRENT_DATE + INTERVAL '2 months')"
        elif type_val == "ano_passado":
            cond = f"{col_name} >= date_trunc('year', CURRENT_DATE - INTERVAL '1 year') AND {col_name} < date_trunc('year', CURRENT_DATE)"
        elif type_val == "este_ano":
            cond = f"{col_name} >= date_trunc('year', CURRENT_DATE) AND {col_name} < date_trunc('year', CURRENT_DATE + INTERVAL '1 year')"
        elif type_val == "proximo_ano":
            cond = f"{col_name} >= date_trunc('year', CURRENT_DATE + INTERVAL '1 year') AND {col_name} < date_trunc('year', CURRENT_DATE + INTERVAL '2 years')"
        elif type_val == "periodo" and (start or end):
            cs = []
            if start:
                cs.append(f"{col_name} >= %s")
                p.append(start)
            if end:
                cs.append(f"{col_name} <= %s")
                p.append(end)
            if cs:
                cond = " AND ".join(cs)
        return cond or None, p

    v_cond, v_params = get_date_cond("data_vencimento", vencimento, vencimento_inicio, vencimento_fim)
    if v_cond:
        where_clauses.append(f"({v_cond})")
        params.extend(v_params)

    p_cond, p_params = get_date_cond("data_pagamento", pagamento, pagamento_inicio, pagamento_fim)
    if p_cond:
        where_clauses.append(f"({p_cond})")
        params.extend(p_params)

    query = f"""
        SELECT
            card_code, card_name, nome_fantasia, cnpj_cpf,
            COUNT(*) as qtd_notas,
            SUM(CASE WHEN %s THEN valor_total ELSE saldo_pendente END) as saldo_total,
            SUM(CASE 
                WHEN %s THEN (CASE WHEN data_pagamento > data_vencimento THEN valor_total ELSE 0 END)
                ELSE (CASE WHEN data_vencimento < CURRENT_DATE THEN saldo_pendente ELSE 0 END)
            END) as saldo_atrasado,
            SUM(CASE 
                WHEN %s THEN (CASE WHEN data_pagamento <= data_vencimento THEN valor_total ELSE 0 END)
                ELSE (CASE WHEN data_vencimento >= CURRENT_DATE THEN saldo_pendente ELSE 0 END)
            END) as saldo_no_prazo,
            MIN(CASE WHEN data_vencimento < CURRENT_DATE THEN data_vencimento END) as venc_atrasado_mais_antigo,
            SUM(CASE WHEN data_vencimento < CURRENT_DATE THEN 1 ELSE 0 END) as qtd_atrasadas,
            SUM(CASE WHEN data_vencimento >= CURRENT_DATE THEN 1 ELSE 0 END) as qtd_no_prazo,
            STRING_AGG(DISTINCT responsavel, ', ') as responsaveis
        FROM notas_cobranca
        WHERE {" AND ".join(where_clauses)}
        GROUP BY card_code, card_name, nome_fantasia, cnpj_cpf
    """
    cursor.execute(query, params)
    resumo = cursor.fetchone()

    cursor.execute("SELECT observacao, atualizado_por, atualizado_em FROM observacoes_cliente WHERE card_code = %s", (card_code,))
    obs = cursor.fetchone()
    
    cursor.close()
    conn.close()
    return {"resumo": resumo, "observacao_geral": obs}

@app.get("/api/clientes/{card_code}/notas")
def get_notas_cliente(
    card_code: str, 
    pago: bool = False,
    vencimento: Optional[str] = None,
    vencimento_inicio: Optional[str] = None,
    vencimento_fim: Optional[str] = None,
    pagamento: Optional[str] = None,
    pagamento_inicio: Optional[str] = None,
    pagamento_fim: Optional[str] = None
):
    """Retorna faturas filtradas do cliente"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    where_clauses = ["card_code = %s"]
    params = [card_code]
    
    if pago:
        where_clauses.append("data_pagamento IS NOT NULL")
    else:
        where_clauses.append("saldo_pendente > 0")

    def get_date_cond(col_name, type_val, start, end):
        if not type_val: return None, []
        p = []
        cond = ""
        if type_val == "semana_passada":
            cond = f"{col_name} >= date_trunc('week', CURRENT_DATE - INTERVAL '1 week') AND {col_name} < date_trunc('week', CURRENT_DATE)"
        elif type_val == "esta_semana":
            cond = f"{col_name} >= date_trunc('week', CURRENT_DATE) AND {col_name} < date_trunc('week', CURRENT_DATE + INTERVAL '1 week')"
        elif type_val == "proxima_semana":
            cond = f"{col_name} >= date_trunc('week', CURRENT_DATE + INTERVAL '1 week') AND {col_name} < date_trunc('week', CURRENT_DATE + INTERVAL '2 weeks')"
        elif type_val == "mes_passado":
            cond = f"{col_name} >= date_trunc('month', CURRENT_DATE - INTERVAL '1 month') AND {col_name} < date_trunc('month', CURRENT_DATE)"
        elif type_val == "este_mes":
            cond = f"{col_name} >= date_trunc('month', CURRENT_DATE) AND {col_name} < date_trunc('month', CURRENT_DATE + INTERVAL '1 month')"
        elif type_val == "proximo_mes":
            cond = f"{col_name} >= date_trunc('month', CURRENT_DATE + INTERVAL '1 month') AND {col_name} < date_trunc('month', CURRENT_DATE + INTERVAL '2 months')"
        elif type_val == "ano_passado":
            cond = f"{col_name} >= date_trunc('year', CURRENT_DATE - INTERVAL '1 year') AND {col_name} < date_trunc('year', CURRENT_DATE)"
        elif type_val == "este_ano":
            cond = f"{col_name} >= date_trunc('year', CURRENT_DATE) AND {col_name} < date_trunc('year', CURRENT_DATE + INTERVAL '1 year')"
        elif type_val == "proximo_ano":
            cond = f"{col_name} >= date_trunc('year', CURRENT_DATE + INTERVAL '1 year') AND {col_name} < date_trunc('year', CURRENT_DATE + INTERVAL '2 years')"
        elif type_val == "periodo" and (start or end):
            cs = []
            if start:
                cs.append(f"{col_name} >= %s")
                p.append(start)
            if end:
                cs.append(f"{col_name} <= %s")
                p.append(end)
            if cs:
                cond = " AND ".join(cs)
        return cond or None, p

    v_cond, v_params = get_date_cond("data_vencimento", vencimento, vencimento_inicio, vencimento_fim)
    if v_cond:
        where_clauses.append(f"({v_cond})")
        params.extend(v_params)

    p_cond, p_params = get_date_cond("data_pagamento", pagamento, pagamento_inicio, pagamento_fim)
    if p_cond:
        where_clauses.append(f"({p_cond})")
        params.extend(p_params)

    query = f"SELECT * FROM notas_cobranca WHERE {' AND '.join(where_clauses)} ORDER BY data_vencimento ASC"
    cursor.execute(query, params)
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return resultados

@app.put("/api/clientes/{card_code}/observacao")
def salvar_observacao_cliente(card_code: str, body: ObservacaoCliente):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            INSERT INTO observacoes_cliente (card_code, observacao, atualizado_por, atualizado_em)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (card_code) DO UPDATE
            SET observacao = EXCLUDED.observacao,
                atualizado_por = EXCLUDED.atualizado_por,
                atualizado_em = CURRENT_TIMESTAMP
            RETURNING *;
        """, (card_code, body.observacao, body.atualizado_por))
        resultado = cursor.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
    return resultado

@app.get("/api/notas/{doc_entry}/historico")
def get_historico(doc_entry: int):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = """
        SELECT *
        FROM historico_cobranca
        WHERE doc_entry = %s
        ORDER BY data_hora DESC
    """
    cursor.execute(query, (doc_entry,))
    resultados = cursor.fetchall()
    cursor.close()
    conn.close()
    return resultados

@app.post("/api/notas/{doc_entry}/historico")
def add_historico(doc_entry: int, historico: HistoricoCreate):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = """
        INSERT INTO historico_cobranca (doc_entry, responsavel, acao, observacao, data_promessa)
        VALUES (%s, %s, %s, %s, %s) RETURNING *;
    """
    try:
        cursor.execute(query, (doc_entry, historico.responsavel, historico.acao, historico.observacao, historico.data_promessa or None))
        novo_registro = cursor.fetchone()
        
        # Atualiza a nota principal com o novo responsavel, status (acao) e observacoes
        update_query = "UPDATE notas_cobranca SET responsavel = %s, status_cobranca = %s, observacoes = %s WHERE doc_entry = %s"
        cursor.execute(update_query, (historico.responsavel, historico.acao, historico.observacao, doc_entry))
        
        if historico.data_promessa:
            cursor.execute("UPDATE notas_cobranca SET data_promessa = %s WHERE doc_entry = %s",
                           (historico.data_promessa, doc_entry))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
        
    return novo_registro

@app.put("/api/notas/{doc_entry}")
def update_nota(doc_entry: int, body: NotaUpdate):
    """Atualiza campos financeiros e de identificação de uma nota."""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Pega apenas os campos que foram enviados no JSON
    fields = body.model_dump(exclude_unset=True)
    
    if not fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    set_clause = ", ".join([f"{k} = %s" for k in fields])
    values = list(fields.values()) + [doc_entry]

    try:
        cursor.execute(
            f"UPDATE notas_cobranca SET {set_clause}, data_atualizacao = NOW() WHERE doc_entry = %s RETURNING *",
            values
        )
        updated = cursor.fetchone()
        if not updated:
            raise HTTPException(status_code=404, detail="Nota não encontrada.")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

    return updated

@app.post("/api/sync")
def trigger_sync():
    """Executa a sincronização delta com o SAP baseada na última atualização"""
    conn = get_db()
    cursor = conn.cursor()
    # Pega o timestamp da última sincronização geral
    cursor.execute("SELECT MAX(data_atualizacao) FROM notas_cobranca")
    last_sync = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    # Formata a data para o padrão YYYY-MM-DD exigido pelo Service Layer
    # Usamos UpdateDate ge 'YYYY-MM-DD'
    since_date = last_sync.strftime('%Y-%m-%d') if last_sync else None
    
    try:
        res_invoices = sync_invoices(since_date=since_date)
        res_recebidas = sync_recebidas(since_date=since_date)
        
        return {
            "status": "success",
            "invoices": res_invoices,
            "pagamentos_novos": res_recebidas
        }
    except Exception as e:
        print(f"❌ Erro na sincronização: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sync/status")
def get_sync_status():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(data_atualizacao) FROM notas_cobranca")
    last_sync = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return {"last_sync": last_sync}

# --- Autenticação ---
@app.get("/api/usuarios")
def list_usuarios():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT username FROM usuarios ORDER BY username ASC")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return [u["username"] for u in users]

@app.post("/api/login")
def login(req: LoginRequest):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM usuarios WHERE username = %s AND password = %s", (req.username, req.password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    
    token = jwt.encode({
        "username": user["username"],
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }, SECRET_KEY, algorithm=ALGORITHM)
    
    return {"token": token, "username": user["username"]}

@app.get("/api/contas-razao")
def list_contas_razao():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT DISTINCT conta_razao_codigo, conta_razao_nome 
        FROM notas_cobranca 
        WHERE conta_razao_codigo IS NOT NULL AND conta_razao_codigo != ''
        ORDER BY conta_razao_nome ASC
    """)
    contas = cursor.fetchall()
    cursor.close()
    conn.close()
    return contas

# Servindo o Frontend Dinâmico (Vanilla HTML/JS) incrustado
@app.get("/", response_class=HTMLResponse)
def get_frontend():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return html_content

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
