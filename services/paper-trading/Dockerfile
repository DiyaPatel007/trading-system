FROM python:3.12-slim

WORKDIR /app

COPY services/paper-trading/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/schemas /libs/schemas
RUN pip install --no-cache-dir -e /libs/schemas

COPY services/paper-trading/app ./app

COPY services/risk-engine/app/risk.py ./app/risk_engine.py

CMD ["python", "-c", "print('paper-trading image ready -- run with docker compose run')"]