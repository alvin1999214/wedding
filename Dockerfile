# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home wedding && mkdir -p /app/data && chown wedding:wedding /app/data
USER wedding
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--preload", "--access-logfile", "-", "app:app"]
