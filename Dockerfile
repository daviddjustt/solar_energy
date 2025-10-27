# ========= Base image =========
FROM python:3.12.4-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:${PATH}"

# ========= Builder stage =========
FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
# Instalar depêndencias em diretório isolado (sem newrelic aqui)
RUN pip install --no-cache-dir --target=/packages -r requirements.txt

# ========= Runtime stage =========
FROM base AS runtime

# Copiar pacotes instalados
COPY --from=builder /packages /usr/local/lib/python3.12/site-packages

# Copiar código
WORKDIR /app
COPY . .

# Garantir que o newrelic está instalado no ambiente final (binário visível)
RUN pip install --no-cache-dir newrelic==10.3.1

# Adicionar usuário não-root
RUN useradd -m nonroot
USER nonroot

EXPOSE 8000

# Comando de inicialização (New Relic + Gunicorn + Django)
CMD ["newrelic-admin", "run-program", "gunicorn", "--bind", "0.0.0.0:${PORT}", "--access-logfile", "-", "solar.wsgi:application"]
