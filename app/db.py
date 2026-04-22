import psycopg2
from psycopg2.extras import RealDictCursor
from .config import get_db_settings


def get_db_connection():
    settings = get_db_settings()
    return psycopg2.connect(**settings)


def get_dict_cursor(conn):
    return conn.cursor(cursor_factory=RealDictCursor)
