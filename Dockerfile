FROM python:3.12-slim

# Definir diretório de trabalho
WORKDIR /code

# Variáveis de ambiente Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt /code/

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . /code/

# Criar usuário não-root
RUN groupadd -r nonroot && \
    useradd -r -g nonroot -u 65532 nonroot

# Criar diretórios necessários e dar permissões
RUN mkdir -p /code/staticfiles /code/media && \
    chown -R nonroot:nonroot /code

# Copiar e dar permissões ao entrypoint
COPY --chown=nonroot:nonroot entrypoint.sh /code/
RUN chmod +x /code/entrypoint.sh

# Mudar para usuário não-root
USER nonroot

# Expor porta
EXPOSE 8080

# Comando de inicialização
ENTRYPOINT ["/code/entrypoint.sh"]
