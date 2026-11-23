FROM python:3.12-slim
WORKDIR /app
COPY ctxbomb ./ctxbomb
COPY payloads ./payloads
COPY config ./config
# Monta tu config en /app/config/config.json (usa "host": "0.0.0.0" dentro del contenedor)
EXPOSE 8080
USER nobody
CMD ["python", "-m", "ctxbomb", "serve", "-c", "config/config.json"]
