from datetime import datetime
from typing import Optional, Tuple


def get_date_cond(col_name: str, tipo: Optional[str], inicio: Optional[str], fim: Optional[str]) -> Tuple[Optional[str], list]:
    if not tipo:
        return None, []

    p = []
    cond = ""
    if tipo == "semana_passada":
        cond = f"{col_name} >= date_trunc('week', CURRENT_DATE - INTERVAL '1 week') AND {col_name} < date_trunc('week', CURRENT_DATE)"
    elif tipo == "esta_semana":
        cond = f"{col_name} >= date_trunc('week', CURRENT_DATE) AND {col_name} < date_trunc('week', CURRENT_DATE + INTERVAL '1 week')"
    elif tipo == "proxima_semana":
        cond = f"{col_name} >= date_trunc('week', CURRENT_DATE + INTERVAL '1 week') AND {col_name} < date_trunc('week', CURRENT_DATE + INTERVAL '2 weeks')"
    elif tipo == "mes_passado":
        cond = f"{col_name} >= date_trunc('month', CURRENT_DATE - INTERVAL '1 month') AND {col_name} < date_trunc('month', CURRENT_DATE)"
    elif tipo == "este_mes":
        cond = f"{col_name} >= date_trunc('month', CURRENT_DATE) AND {col_name} < date_trunc('month', CURRENT_DATE + INTERVAL '1 month')"
    elif tipo == "proximo_mes":
        cond = f"{col_name} >= date_trunc('month', CURRENT_DATE + INTERVAL '1 month') AND {col_name} < date_trunc('month', CURRENT_DATE + INTERVAL '2 months')"
    elif tipo == "ano_passado":
        cond = f"{col_name} >= date_trunc('year', CURRENT_DATE - INTERVAL '1 year') AND {col_name} < date_trunc('year', CURRENT_DATE)"
    elif tipo == "este_ano":
        cond = f"{col_name} >= date_trunc('year', CURRENT_DATE) AND {col_name} < date_trunc('year', CURRENT_DATE + INTERVAL '1 year')"
    elif tipo == "proximo_ano":
        cond = f"{col_name} >= date_trunc('year', CURRENT_DATE + INTERVAL '1 year') AND {col_name} < date_trunc('year', CURRENT_DATE + INTERVAL '2 years')"
    elif tipo == "periodo" and (inicio or fim):
        cs = []
        if inicio:
            cs.append(f"{col_name} >= %s")
            p.append(inicio)
        if fim:
            cs.append(f"{col_name} <= %s")
            p.append(fim)
        if cs:
            cond = " AND ".join(cs)

    return (cond or None), p


def normalize_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    return date_str.split("T")[0]


def format_date_br(date_str: Optional[str]) -> str:
    if not date_str:
        return "N/A"
    try:
        parsed = datetime.strptime(date_str.split("T")[0], "%Y-%m-%d")
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return date_str
