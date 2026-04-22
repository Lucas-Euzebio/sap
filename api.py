from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from app.db import get_db_connection
from app.sync import sync_invoices, sync_recebidas

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
    pagamento_fim: Optional[str] = None
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
        where_clauses.append("(card_name ILIKE %s OR card_code ILIKE %s)")
        params.extend([f"%{cliente}%", f"%{cliente}%"])
    if responsavel:
        where_clauses.append("responsavel ILIKE %s")
        params.append(f"%{responsavel}%")

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
        
        # Atualiza a nota principal com o novo responsavel e status se houver promessa
        update_query = "UPDATE notas_cobranca SET responsavel = %s, observacoes = %s WHERE doc_entry = %s"
        cursor.execute(update_query, (historico.responsavel, historico.observacao, doc_entry))
        
        if historico.data_promessa:
            cursor.execute("UPDATE notas_cobranca SET status_cobranca = %s, data_promessa = %s WHERE doc_entry = %s",
                           ('Promessa de Pagamento', historico.data_promessa, doc_entry))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
        
    return novo_registro

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
    
    res_invoices = sync_invoices(since_date=since_date)
    res_recebidas = sync_recebidas(since_date=since_date)
    
    return {
        "status": "success",
        "invoices": res_invoices,
        "pagamentos_novos": res_recebidas
    }

@app.get("/api/sync/status")
def get_sync_status():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(data_atualizacao) FROM notas_cobranca")
    last_sync = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return {"last_sync": last_sync}

# Servindo o Frontend Dinâmico (Vanilla HTML/JS) incrustado
@app.get("/", response_class=HTMLResponse)
def get_frontend():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return html_content

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
