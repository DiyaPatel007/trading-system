FROM python:3.12-slim

WORKDIR /app

COPY services/scanner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/schemas /libs/schemas
RUN pip install --no-cache-dir -e /libs/schemas

COPY services/scanner/app ./app

# app/risk_engine.py is copied in from the single source of truth at
# services/risk-engine/app/risk.py, NOT maintained as a second hand-
# written copy -- see the note at the top of app/run_scan.py.
COPY services/risk-engine/app/risk.py ./app/risk_engine.py

CMD ["python", "-c", "print('scanner image ready -- run with docker compose run')"]