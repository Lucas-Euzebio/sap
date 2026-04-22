from app.sync import sync_recebidas
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sincroniza pagamentos confirmados do SAP para o Banco Local")
    parser.add_argument("--since-date", type=str, help="Considerar apenas pagamentos de X data pra cá (YYYY-MM-DD)")
    args = parser.parse_args()
    sync_recebidas(since_date=args.since_date)
