# syntax=docker/dockerfile:1
# ── La Poste Tunisienne — National Reporting (Flask + SQL Server client) ──────
# Pinned to Debian 12 (bookworm) to match the Microsoft ODBC apt repository.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=wsgi.py

# ── System deps + Microsoft ODBC Driver 18 (for pyodbc → SQL Server) ──────────
# The MS prod.list references /usr/share/keyrings/microsoft-prod.gpg, so the key
# must be dearmored to exactly that path.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates apt-transport-https \
        unixodbc-dev gcc g++ \
 && mkdir -p /usr/share/keyrings \
 && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list \
        -o /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps (cached layer) ────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install -r requirements.txt

# ── App source ────────────────────────────────────────────────────────────────
COPY . .
RUN sed -i 's/\r$//' docker/entrypoint.sh \
 && chmod +x docker/entrypoint.sh \
 && mkdir -p /app/reports /app/uploads \
 && useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
