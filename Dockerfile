FROM python:3.12.4-slim AS base

FROM base AS builder
RUN apt-get update && apt-get -y install libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY ./requirements.txt requirements.txt
RUN pip3 install --no-cache-dir --target=/packages -r requirements.txt

FROM base AS runtime
# Instalar dependências diretamente no runtime para ter os executáveis
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Security Context
RUN useradd -m nonroot
USER nonroot

COPY . code
WORKDIR code
EXPOSE 8000

# Run the production server with New Relic
CMD python -m newrelic.admin run-program gunicorn --bind 0.0.0.0:$PORT --access-logfile - solar.wsgi:application

