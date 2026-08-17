FROM python:3.12-slim

WORKDIR /app

COPY services/data-pipeline/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared schemas package -- same pattern as core-api (Module 1)
COPY libs/schemas /libs/schemas
RUN pip install --no-cache-dir -e /libs/schemas

COPY services/data-pipeline/app ./app

# This service has no long-running server -- it's run as one-off jobs:
#   docker compose run --rm data-pipeline python -m app.ingestion.fetch_historical
#   docker compose run --rm data-pipeline python -m app.features.compute_features
CMD ["python", "-c", "print('data-pipeline image ready -- run a specific job with docker compose run')"]
