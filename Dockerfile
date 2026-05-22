FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Fetch Chart.js + date adapter at build time (runtime is offline / self-hosted)
RUN mkdir -p /srv/app/static/vendor \
 && curl -fsSL https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js \
      -o /srv/app/static/vendor/chart.umd.min.js \
 && curl -fsSL https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js \
      -o /srv/app/static/vendor/chartjs-adapter-date-fns.bundle.min.js

RUN mkdir -p /data
VOLUME ["/data"]

ENV DATA_DIR=/data \
    HOST_APP_DATA_ROOT=/home/umbrel/umbrel/app-data \
    CONTAINER_APP_DATA_ROOT=/host-app-data

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000", "--no-access-log"]
