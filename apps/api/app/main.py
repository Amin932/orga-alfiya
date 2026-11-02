"""Base de l'API, sans routes métier ouvertes avant l'authentification."""
import os
from contextlib import closing

import psycopg
from fastapi import FastAPI, HTTPException

app = FastAPI(
    title="Orga Alfiya API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Vérification de disponibilité non sensible."""
    return {"status": "ok", "service": "orga-alfiya-api"}


@app.get("/api/health/database")
def database_health() -> dict[str, str]:
    """Vérification de la connectivité PostgreSQL (sans exposer la configuration)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        with closing(psycopg.connect(url, connect_timeout=3)) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ok", "database": "connected"}
