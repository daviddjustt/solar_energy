import os
from .common import Common
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Production(Common):
    # Herda os apps do common.py e adiciona o gunicorn
    INSTALLED_APPS = Common.INSTALLED_APPS + ("gunicorn", )
    
    SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
    ALLOWED_HOSTS = ["*"]

    # ==========================================
    # FILE UPLOAD SETTINGS
    # ==========================================
    FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 MB
    DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 MB
    
    # As configurações de Cloudinary e Arquivos Estáticos (Static) 
    # já estão sendo herdadas perfeitamente do common.py! 
    # Não precisamos repeti-las aqui.

    # ==========================================
    # SEGURANÇA EM PRODUÇÃO (RAILWAY)
    # ==========================================
    # Garante que o Django entenda o HTTPS do Railway e não dê loop infinito
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True