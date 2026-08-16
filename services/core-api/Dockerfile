FROM python:3.12-slim

WORKDIR /app

# System deps needed to build psycopg's binary wheel cleanly on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY services/core-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared schemas package -- installed so core-api (and every later
# service) imports the exact same Candle/Trade/Signal/RiskAssessment types
COPY libs/schemas /libs/schemas
RUN pip install --no-cache-dir -e /libs/schemas

COPY services/core-api/app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
