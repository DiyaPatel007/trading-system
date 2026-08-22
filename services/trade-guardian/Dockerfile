FROM python:3.12-slim

WORKDIR /app

COPY services/trade-guardian/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/schemas /libs/schemas
RUN pip install --no-cache-dir -e /libs/schemas

COPY services/trade-guardian/app ./app

CMD ["python", "-c", "print('trade-guardian image ready -- run with docker compose run')"]