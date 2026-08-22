FROM python:3.12-slim

WORKDIR /app

COPY services/mcp-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/schemas /libs/schemas
RUN pip install --no-cache-dir -e /libs/schemas

COPY services/mcp-server/app ./app

COPY services/risk-engine/app/risk.py ./app/risk_engine.py

CMD ["python", "-m", "app.server"]