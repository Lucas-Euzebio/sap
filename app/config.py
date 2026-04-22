import os
from dotenv import load_dotenv

load_dotenv()


def env(name: str, default=None):
    return os.getenv(name, default)


def get_db_settings():
    return {
        "host": env("DB_HOST", "localhost"),
        "port": env("DB_PORT", "5432"),
        "dbname": env("DB_NAME", "sap_cobrancas"),
        "user": env("DB_USER", "postgres"),
        "password": env("DB_PASS", "postgres"),
    }


def get_sap_url():
    sap_url = env("SAP_URL")
    if not sap_url:
        raise ValueError("SAP_URL não definido no .env")
    return sap_url.rstrip("/")


def get_sap_auth_payload():
    return {
        "CompanyDB": env("COMPANY_DB"),
        "UserName": env("USERNAME"),
        "Password": env("PASSWORD"),
    }
