FROM python:3.11-slim

LABEL project="TRACE_PD"
LABEL description="Trace Personal Behavior Debugger — FastAPI Backend"

WORKDIR /app

# System deps needed for psycopg2 / scikit-learn
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd --system trcpd && useradd --system --gid trcpd --no-create-home trcpd \
    && chown -R trcpd:trcpd /app
USER trcpd

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]
