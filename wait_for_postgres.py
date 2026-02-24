import os
import logging
from time import time, sleep
import psycopg2

# Pega a URL completa do Railway
DATABASE_URL = os.getenv("DATABASE_URL")
CHECK_TIMEOUT = int(os.getenv("POSTGRES_CHECK_TIMEOUT", 40)) # Aumentei um pouco
CHECK_INTERVAL = 2

logger = logging.getLogger()
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())

def pg_isready():
    start_time = time()
    logger.info("⏳ Iniciando verificação do banco de dados...")

    while time() - start_time < CHECK_TIMEOUT:
        try:
            # Conecta usando a URL completa diretamente
            conn = psycopg2.connect(DATABASE_URL)
            logger.info("✅ Postgres está pronto e a senha está correta! ✨ 💅")
            conn.close()
            return True
        except psycopg2.OperationalError as e:
            error_msg = str(e)
            # Se o erro for de senha, não adianta esperar, o script deve parar!
            if "password authentication failed" in error_msg:
                logger.error("❌ ERRO FATAL: Senha do banco incorreta!")
                logger.error(f"Detalhes: {error_msg}")
                return False
            
            logger.info(f"😴 Banco ainda não disponível... (Tentando novamente)")
            sleep(CHECK_INTERVAL)

    logger.error(f"❌ Timeout: Não conseguimos conectar após {CHECK_TIMEOUT}s.")
    return False

if __name__ == "__main__":
    if not pg_isready():
        exit(1) # Para o deploy se o banco não estiver ok