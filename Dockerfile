FROM python:3.12-slim

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependências do sistema e utilitários de texto
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar requisitos
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo o projeto
COPY . /code/

# Criar usuário nonroot
RUN groupadd -r nonroot && \
    useradd -r -g nonroot -u 65532 nonroot

# Criar diretórios necessários e ajustar permissões iniciais
RUN mkdir -p /code/staticfiles /code/media /app/media && \
    chown -R nonroot:nonroot /code /app

# Corrigir permissões e formato do entrypoint
RUN dos2unix /code/entrypoint.sh && \
    chmod +x /code/entrypoint.sh

EXPOSE 8080

# Mantemos como root para o entrypoint configurar o volume /app/media
# O entrypoint usará 'exec' para rodar o gunicorn
ENTRYPOINT ["/code/entrypoint.sh"]