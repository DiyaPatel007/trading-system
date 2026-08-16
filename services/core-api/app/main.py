"""
core-api: the first working service in the trading system.

Its only responsibility right now is /health -- proving Postgres and
Redis are reachable from inside the Docker network. Every later module
(market data, risk engine, scanner, paper trading) will be added as new
routers/services that build on this same skeleton.
"""

from datetime import datetime, timezone

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from .db import check_postgres, check_redis

app = FastAPI(
    title="Adaptive AI Trading System - Core API",
    version="0.1.0",
)


@app.get("/health")
def health():
    pg_ok, pg_detail = check_postgres()
    redis_ok, redis_detail = check_redis()
    overall_ok = pg_ok and redis_ok

    body = {
        "status": "ok" if overall_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {
            "postgres": {"ok": pg_ok, "detail": pg_detail},
            "redis": {"ok": redis_ok, "detail": redis_detail},
        },
    }
    code = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=body, status_code=code)


@app.get("/")
def root():
    return {"service": "core-api", "status": "running"}
