import psycopg2
from dotenv import load_dotenv
from app.config import get_db_settings


def setup_database():
    load_dotenv()
    
    settings = get_db_settings()
    db_host = settings['host']
    db_port = settings['port']
    db_name = settings['dbname']
    db_user = settings['user']
    db_pass = settings['password']
    
    print(f"🔄 Conectando ao PostgreSQL local em {db_host}:{db_port}...")
    
    try:
        # Primeiro conecta no banco padrao "postgres" apenas para criar o banco de dados novo se ele não existir
        conn = psycopg2.connect(host=db_host, port=db_port, user=db_user, password=db_pass, dbname="postgres")
        conn.autocommit = True
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'sap_cobrancas'")
        exists = cursor.fetchone()
        if not exists:
            print("📦 Criando banco de dados 'sap_cobrancas'...")
            cursor.execute("CREATE DATABASE sap_cobrancas")
        else:
            print("📦 Banco de dados 'sap_cobrancas' já existe.")
            
        cursor.close()
        conn.close()
        
        # Agora conecta no banco recém criado/existente para montar as tabelas
        conn = psycopg2.connect(host=db_host, port=db_port, user=db_user, password=db_pass, dbname=db_name)
        cursor = conn.cursor()
        
        create_table_query = """
        CREATE TABLE IF NOT EXISTS notas_cobranca (
            id SERIAL PRIMARY KEY,
            doc_entry INTEGER UNIQUE NOT NULL,    -- ID Interno do SAP
            doc_num INTEGER,                      -- DocNum original do SAP
            numero_documento VARCHAR(50),         -- SequenceSerial
            nfse VARCHAR(50),                     -- U_TX_NDfe
            card_code VARCHAR(50),                -- Código do Cliente
            card_name VARCHAR(255),               -- Razão Social
            nome_fantasia VARCHAR(255),           -- CardForeignName
            cnpj_cpf VARCHAR(20),                 
            data_emissao DATE,
            data_vencimento DATE,
            valor_total NUMERIC(15, 2),
            saldo_pendente NUMERIC(15, 2),
            conta_razao_codigo VARCHAR(50),
            conta_razao_nome VARCHAR(255),
            banco TEXT,
            data_pagamento DATE,
            
            -- Campos Específicos do Sistema de Acompanhamento
            status_cobranca VARCHAR(50) DEFAULT 'Pendente', 
            responsavel VARCHAR(100),
            observacoes TEXT,
            data_promessa DATE,
            
            data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        cursor.execute(create_table_query)
        conn.commit()
        
        print("✅ Tabela 'notas_cobranca' criada/verificada com sucesso!")

        create_observacoes_query = """
        CREATE TABLE IF NOT EXISTS observacoes_cliente (
            id SERIAL PRIMARY KEY,
            card_code VARCHAR(50) UNIQUE NOT NULL,
            observacao TEXT,
            atualizado_por VARCHAR(100),
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_observacoes_query)
        conn.commit()
        print("✅ Tabela 'observacoes_cliente' criada/verificada com sucesso!")

        create_historico_query = """
        CREATE TABLE IF NOT EXISTS historico_cobranca (
            id SERIAL PRIMARY KEY,
            doc_entry INTEGER NOT NULL,
            responsavel VARCHAR(100) NOT NULL,
            acao VARCHAR(100) NOT NULL,
            observacao TEXT,
            data_promessa DATE,
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_historico_query)
        conn.commit()
        print("✅ Tabela 'historico_cobranca' criada/verificada com sucesso!")

        create_usuarios_query = """
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_usuarios_query)
        conn.commit()
        print("✅ Tabela 'usuarios' criada/verificada com sucesso!")
        
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ Erro ao configurar banco de dados: {e}")

if __name__ == "__main__":
    setup_database()
