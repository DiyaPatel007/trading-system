FROM python:3.12-slim

WORKDIR /app

COPY services/regime-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/regime-engine/app ./app

CMD ["python", "-c", "print('regime-engine image ready -- run with docker compose run')"]