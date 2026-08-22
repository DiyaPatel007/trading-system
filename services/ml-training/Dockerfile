FROM python:3.12-slim

WORKDIR /app

COPY services/ml-training/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ml-training/app ./app

# Trained model artifacts (joblib files) are written here -- mounted as
# a volume in docker-compose.yml so they survive container restarts and
# are visible on the host, not trapped inside a container filesystem.
RUN mkdir -p /app/models

CMD ["python", "-c", "print('ml-training image ready -- run with docker compose run')"]