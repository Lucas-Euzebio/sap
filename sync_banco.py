from app.sync import sync_invoices
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sincroniza notas em aberto do SAP para o Banco Local")
    parser.add_argument("--since-date", type=str, help="Considerar apenas notas criadas de X data pra cá (Formato: YYYY-MM-DD)")
    args = parser.parse_args()
    sync_invoices(since_date=args.since_date)
