FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir \
    fastapi uvicorn httpx google-cloud-firestore google-auth "pydantic>=2"

COPY services/__init__.py services/__init__.py
COPY services/ui/ services/ui/

CMD exec uvicorn services.ui.main:app --host 0.0.0.0 --port ${PORT:-8080}
