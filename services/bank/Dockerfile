FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
# Keep this list in step with pyproject.toml's dependencies. It is spelled out rather than
# installed from the project so the layer caches on its own, but that means a dependency
# added to pyproject alone is silently missing at runtime — which is exactly how Model Armor
# came up "unavailable" in production while passing every test locally.
RUN pip install --no-cache-dir \
    google-adk "a2a-sdk[http-server]" httpx google-cloud-aiplatform google-cloud-bigquery \
    google-cloud-firestore google-cloud-pubsub google-cloud-modelarmor \
    fastapi uvicorn "pydantic>=2" pyyaml

# Local Gemma for the perimeter gate: prebuilt CPU wheel (no toolchain, no compile) plus the
# quantised model baked into the image, so the gate never calls out to inspect text.
RUN pip install --no-cache-dir llama-cpp-python \
      --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
    || echo "llama-cpp unavailable; perimeter gate will run on deterministic rules only"
# 4B is the smallest Gemma that actually classifies rather than answering one word to
# everything — see the measured comparison in services/bank/redaction/gemma.py
ADD https://huggingface.co/unsloth/gemma-3-4b-it-GGUF/resolve/main/gemma-3-4b-it-Q4_K_M.gguf \
    /app/models/gemma-3-4b-it-Q4_K_M.gguf

COPY services/ services/

# BANK env var selects the fleet identity; service account is ambient on Cloud Run
CMD exec uvicorn services.bank.api.main:app --host 0.0.0.0 --port ${PORT:-8080}
