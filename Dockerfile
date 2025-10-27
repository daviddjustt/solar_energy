# ========================================
# Stage 1: Base image
# ========================================
FROM python:3.12.4-slim AS base

# ========================================
# Stage 2: Builder (compilação)
# ========================================
FROM base AS builder

# Instalar dependências de compilação
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY ./requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --target=/packages -r /tmp/requirements.txt

# ========================================
# Stage 3: Runtime (produção)
# ========================================
FROM base AS runtime

# Instalar bibliotecas runtime necessárias
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python diretamente
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Criar usuário não-root para segurança
RUN useradd -m -u 1000 nonroot

# Copiar código da aplicação
WORKDIR /code
COPY --chown=nonroot:nonroot . /code/

# Copiar e configurar scripts de inicialização
COPY --chown=nonroot:nonroot entrypoint.sh create_admin_now.py /code/

# Tornar o entrypoint executável
RUN chmod +x /code/entrypoint.sh

# Mudar para usuário não-root
USER nonroot

# Expor porta
EXPOSE 8000

# Usar o script de inicialização
CMD ["/code/entrypoint.sh"]
