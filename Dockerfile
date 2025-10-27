FROM python:3.12.4-slim AS runtime

# Garante que /usr/local/bin esteja no PATH mesmo após troca de usuário
ENV PATH="/usr/local/bin:$PATH"

# Copiar libs do builder
COPY --from=builder /packages /usr/local/lib/python3.12/site-packages

WORKDIR /app
COPY . .

# Reinstalar New Relic para registrar o binário globalmente
RUN pip install --no-cache-dir newrelic==10.3.1

# Verificação: cria um link simbólico caso a permissão restrinja o PATH
RUN ln -s $(python -m site --user-base)/bin/newrelic-admin /usr/local/bin/newrelic-admin || true

RUN useradd -m nonroot
USER nonroot

EXPOSE 8000
CMD ["newrelic-admin", "run-program", "gunicorn", "--bind", "0.0.0.0:${PORT}", "--access-logfile", "-", "solar.wsgi:application"]
