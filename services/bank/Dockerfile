FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    google-adk a2a-sdk google-cloud-aiplatform google-cloud-bigquery \
    google-cloud-firestore google-cloud-pubsub fastapi uvicorn "pydantic>=2" pyyaml

COPY services/ services/

# BANK env var selects the fleet identity; service account is ambient on Cloud Run
CMD exec uvicorn services.bank.api.main:app --host 0.0.0.0 --port ${PORT:-8080}
