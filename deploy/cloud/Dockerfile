FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer libreoffice-calc fonts-noto-cjk tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY requirements*.txt ./
# CPU-only; no paid GPU/CUDA runtime in the cost-first deployment.
RUN python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 && python -m pip install -r requirements-semantic.txt -r requirements-llm.txt -r requirements-docling.txt
COPY app ./app
COPY scripts ./scripts
COPY config ./config
COPY web ./web
COPY deploy ./deploy
COPY CLOUD-DEMO.json ./CLOUD-DEMO.json
RUN mkdir -p /app/runtime/tmp /app/.local-home /app/.cache/huggingface/hub /app/.local-config /app/.local-share && useradd --uid 10001 --home-dir /app/.local-home --no-create-home p18 && chown -R p18:p18 /app
USER 10001:10001
CMD ["python", "-B", "deploy/cloud/server.py"]
