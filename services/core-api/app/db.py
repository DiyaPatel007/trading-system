"""
Thin connectivity helpers. Module 1 only needs to prove we can reach
Postgres and Redis -- real query logic arrives in later modules.
"""

import psycopg
import redis

from .config import settings


def check_postgres() -> tuple[bool, str]:
    try:
        with psycopg.connect(settings.postgres_dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return True, "connected"
    except Exception as e:  # noqa: BLE001 -- deliberately broad for a health check
        return False, str(e)


def check_redis() -> tuple[bool, str]:
    try:
        r = redis.Redis(
            host=settings.redis_host, port=settings.redis_port, socket_connect_timeout=3
        )
        r.ping()
        return True, "connected"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
