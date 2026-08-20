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
- **Module 3 (done):** market regime engine (`services/regime-engine`)
  -- rule-based classifier (bullish/bearish/sideways/high_volatility/
  low_volatility/transitional) computed daily from universe-wide trend,
  volatility, and breadth, written to `market_regime`. Thresholds are
  calibrated against real observed NIFTY 50 percentiles, not guessed --
  see the comments at the top of `services/regime-engine/app/regime.py`
  before changing them.
- **Module 4 (done):** risk engine + position sizing
  (`services/risk-engine`) -- pure, DB-free risk calculation
  (`calculate_risk`) and position sizing (`size_position`), each with a
  hard approve/reject gate independent of any ML prediction. No live
  data dependency; fully covered by hand-verified unit tests.
- Module 5 onward: see commit history.

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

**Known corporate-action gotcha:** `services/data-pipeline/app/universe.py`
must be kept in sync with real-world ticker changes (delistings, demergers,
symbol renames) -- Yahoo Finance will 404 on a stale ticker. As of this
module, Tata Motors' demerger and LTIMindtree's rename are already
reflected (`TMPV.NS`/`TMCV.NS`, `LTM.NS`).

**Known Yahoo Finance reliability note:** Yahoo actively rate-limits/blocks
automated requests. `fetch_historical.py` mitigates this with browser
impersonation (via yfinance's built-in curl_cffi support), retry with
exponential backoff (up to 4 attempts/symbol), and a self-imposed delay
between symbols -- but occasional failures for a handful of symbols are
still normal, not a sign something is broken. Re-run with `--symbols` to
retry just the ones that failed.

## Running Module 3

Depends on Module 2 having already populated `candles` and `features`.

```bash
# 1. Apply the migration (same one-time-manual-application note as Module 2)
docker exec -i trading-postgres psql -U trading_user -d trading < db/init/003_market_regime_table.sql

# 2. Compute regime for every day with usable history
docker compose build regime-engine
docker compose run --rm regime-engine python -m app.compute_regime
```

**Verify it worked:**
```bash
docker exec -it trading-postgres psql -U trading_user -d trading -c "SELECT COUNT(*) FROM market_regime;"
docker exec -it trading-postgres psql -U trading_user -d trading -c "SELECT regime, COUNT(*) FROM market_regime GROUP BY regime ORDER BY COUNT(*) DESC;"
```
The regime distribution should NOT be dominated (~99%) by a single
regime -- if it is, the thresholds in `app/regime.py` need recalibrating
against your data's actual percentiles (see the query and worked example
in that recalibration -- ask for it again if needed; the current
thresholds were tuned this way once already).

## Running Module 4

Risk Engine has no database dependency and nothing to "run" against
live data yet -- it's a pure calculation library that Module 5 (Scanner)
will import directly. Verify it with its test suite:

```bash
pip install pytest
python -m pytest tests/test_risk_engine.py -v
```

To build its Docker image (mostly for consistency with other services --
nothing calls it over HTTP yet):
```bash
docker compose build risk-engine
```

## Running the full test suite

**Important:** several services share the package name `app` internally
(correct in production, since each runs in its own container) -- when
running the WHOLE suite together in one process, `tests/_helpers.py`
handles avoiding import collisions between them. Always run the suite
from the repo root:

```bash
pip install pandas pandas-ta numpy pytest httpx psycopg[binary] pydantic pydantic-settings
python -m pytest tests/ -v --ignore=tests/test_health_endpoint.py
```
(`test_health_endpoint.py` is excluded here because it requires the full
Docker stack running on `localhost:8000` -- run it separately after
`docker compose up` if you want to check that too.)