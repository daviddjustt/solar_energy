FROM python:3.12-slim

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependências e dos2unix para garantir compatibilidade de scripts
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /code/

# Configurar usuário e permissões
RUN groupadd -r nonroot && \
    useradd -r -g nonroot -u 65532 nonroot && \
    mkdir -p /code/staticfiles /code/media /app/media && \
    chown -R nonroot:nonroot /code /app

# FORÇAR o formato Linux e a execução do entrypoint
RUN dos2unix /code/entrypoint.sh && \
    chmod +x /code/entrypoint.sh

EXPOSE 8080

# Mantemos root para o entrypoint ajustar o volume /app/media, o gunicorn rodará via exec
ENTRYPOINT ["/code/entrypoint.sh"]