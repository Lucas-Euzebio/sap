import csv
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "sap_cobrancas"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", "postgres")
    )

def import_csv_data(file_path):
    if not os.path.exists(file_path):
        print(f"❌ Erro: Arquivo não encontrado: {file_path}")
        return

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    found_count = 0
    not_found_rows = []
    
    # Abrir CSV
    # Usa utf-8-sig para lidar com o BOM do Excel/Windows se existir
    with open(file_path, mode='r', encoding='utf-8-sig', errors='replace') as f:
        reader = csv.DictReader(f, delimiter=';')
        
        print(f"📋 Colunas detectadas no CSV: {reader.fieldnames}")
        
        count = 0
        for row in reader:
            # Debug das primeiras 3 linhas
            if count < 3:
                print(f"🔍 Analisando linha {count+1}: Código Parceiro='{row.get('Código Parceiro')}', Série='{row.get('Série do Documento')}'")
            count += 1

            card_code = row.get('Código Parceiro', '').strip()
            num_doc = row.get('Série do Documento', '').strip()
            responsavel = row.get('Responsavel', '').strip()
            observacao = row.get('Observações', '').strip()
            nfse_csv = row.get('Número da NFS-e', '').strip()
            
            if not card_code or not num_doc:
                continue

            # Buscar a nota no banco
            cursor.execute("""
                SELECT doc_entry, card_name 
                FROM notas_cobranca 
                WHERE card_code = %s AND (numero_documento = %s OR nfse = %s OR numero_documento = %s)
                LIMIT 1
            """, (card_code, num_doc, num_doc, nfse_csv))
            
            nota = cursor.fetchone()
            
            if nota:
                doc_entry = nota['doc_entry']
                
                # Só atualiza se o responsável no CSV não estiver vazio
                if responsavel:
                    cursor.execute("UPDATE notas_cobranca SET responsavel = %s WHERE doc_entry = %s", (responsavel, doc_entry))
                    
                    if observacao:
                        cursor.execute("""
                            INSERT INTO historico_cobranca (doc_entry, responsavel, acao, observacao)
                            VALUES (%s, %s, %s, %s)
                        """, (doc_entry, responsavel, 'Importação Manual', observacao))
                    
                    found_count += 1
            else:
                if responsavel:
                    not_found_rows.append({
                        'codigo sap': card_code,
                        'serie do documento': num_doc,
                        'responsavel': responsavel
                    })

    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"\n✅ Processamento concluído!")
    print(f"📊 Notas atualizadas: {found_count}")
    
    if not_found_rows:
        print(f"\n⚠️  {len(not_found_rows)} linhas com responsável não foram localizadas no banco de dados:")
        print("-" * 60)
        for row in not_found_rows:
            print(f"Cliente: {row.get('codigo sap')} | Doc: {row.get('serie do documento')} | Resp: {row.get('responsavel')}")
        print("-" * 60)

if __name__ == "__main__":
    csv_path = "/Users/lucaseuzebio/Projetos/sap/pendentes de pagamento 1304.csv"
    import_csv_data(csv_path)
