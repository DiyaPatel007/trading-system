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
- Module 2 onward: see commit history.
