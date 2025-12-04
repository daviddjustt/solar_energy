FROM python:3.12-slim

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar requirements
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicação
COPY . /code/

# ==========================================
# CRIAR USUÁRIO NONROOT
# ==========================================
RUN groupadd -r nonroot && \
    useradd -r -g nonroot -u 65532 nonroot

# ==========================================
# CRIAR DIRETÓRIOS E DAR PERMISSÕES
# ==========================================
RUN mkdir -p /code/staticfiles /code/media /app /app/media && \
    chown -R nonroot:nonroot /code /app && \
    chmod -R 755 /app/media

# Copiar entrypoint e dar permissões
COPY --chown=nonroot:nonroot entrypoint.sh /code/
RUN chmod +x /code/entrypoint.sh

# Makemigrations
# RUN python manage.py makemigrations

# ⚠️ NÃO mudar para usuário nonroot ainda
# Deixar como root para o entrypoint configurar permissões
# USER nonroot

EXPOSE 8080

ENTRYPOINT ["/code/entrypoint.sh"]