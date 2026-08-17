# Adaptive AI-Powered Personal Trading and Risk Management System

## Python version

This project standardizes on **Python 3.12** everywhere: every service's
Dockerfile, every `pyproject.toml`/`requirements.txt`, and local dev
virtualenvs. Do not use 3.11 or 3.13 for this project -- see the Module 1
decision log (or ask in-repo) for the reasoning: broadest current ML/data
library compatibility (scikit-learn, XGBoost, LightGBM, pandas, NumPy,
Hugging Face transformers) with the longest remaining support runway,
while avoiding known 3.13 compatibility gaps in some of our web-stack
dependencies (httpx/h11).

If you use `pyenv`:
```bash
pyenv install 3.12.10
pyenv local 3.12.10   # reads .python-version in this repo
```
`.python-version` pins an exact patch (required by pyenv itself), but the
*minor* version 3.12 is the real project standard -- `requires-python`
in every `pyproject.toml` and the `python:3.12-slim` Docker base image
both float across 3.12.x patches automatically. 3.12.10 is the last
3.12.x release with downloadable installers (3.12 is now in
security-only, source-only maintenance) -- fine for local dev; the
Docker image will still pull whatever patched 3.12 is current inside
containers. Never jump to 3.13 for this project.

## Modules

- **Module 1 (done):** project foundation, shared Pydantic schemas
  (`libs/schemas`), `core-api` service with `/health` endpoint,
  Postgres+TimescaleDB, Redis, Docker Compose.
- **Module 2 (done):** historical data ingestion (`services/data-pipeline`)
  -- fetches NIFTY 50 OHLCV via yfinance into the `candles` table, then
  computes technical indicators (EMA, SMA, RSI, MACD, ATR, volume ratio)
  into the `features` table. See "Running Module 2" below.
- Module 3 onward: see commit history.

## Running Module 2

The data-pipeline service is a **job runner**, not an always-on service --
it's excluded from `docker compose up` by default (via a Compose
"profile") and run explicitly, on demand:

```bash
# 1. Apply the new features-table migration (only needed once; if your
#    postgres container already existed before this migration was added,
#    see the note below)
docker compose up -d postgres
docker exec -i trading-postgres psql -U trading_user -d trading < db/init/002_features_table.sql

# 2. Fetch historical OHLCV for all NIFTY 50 symbols (takes a few minutes)
docker compose run --rm data-pipeline python -m app.ingestion.fetch_historical --period 5y

# 3. Compute indicators from the candles you just fetched
docker compose run --rm data-pipeline python -m app.features.compute_features
```

**Note on the migration:** Compose only runs files in `db/init/` automatically
the *first time* a Postgres container is created (fresh volume). Since your
`trading-postgres` container already exists from Module 1, step 1 above
applies the new migration manually. If you ever wipe the volume and start
fresh (`docker compose down -v`), both `001_` and `002_` run automatically.

**Verify it worked:**
```bash
docker exec -it trading-postgres psql -U trading_user -d trading -c "SELECT COUNT(*) FROM candles;"
docker exec -it trading-postgres psql -U trading_user -d trading -c "SELECT COUNT(*) FROM features;"
docker exec -it trading-postgres psql -U trading_user -d trading -c "SELECT symbol, ts, features->'rsi_14' AS rsi FROM features ORDER BY ts DESC LIMIT 5;"
```
`candles` should have roughly 50 symbols × ~5 years of trading days (~1,250
rows/symbol) = order of 60,000+ rows. `features` will have somewhat fewer,
since warm-up rows (not enough history yet for e.g. SMA-200) are dropped.
