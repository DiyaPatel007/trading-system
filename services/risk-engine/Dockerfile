FROM python:3.12-slim

WORKDIR /app

COPY services/risk-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/schemas /libs/schemas
RUN pip install --no-cache-dir -e /libs/schemas

COPY services/risk-engine/app ./app

CMD ["python", "-c", "print('risk-engine image ready -- imported as a library by other services')"]