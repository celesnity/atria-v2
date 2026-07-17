# Optimize connector image (BACKEND ONLY — the tile stays the vanilla blocks/guided.html served by Core).
# Build context is the REPO ROOT so the image can install the shared minder_python_sdk:
#   docker compose ... up -d --build optimize
FROM python:3.12-slim
WORKDIR /app

# Shared connector SDK first (own layer, rarely changes).
COPY minder_python_sdk /sdk
RUN pip install --no-cache-dir /sdk

# Module's own (light) deps.
COPY modules/optimize_demo/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Connector code + the reused decision engine. service.py adds ./scripts to sys.path in-container.
COPY modules/optimize_demo/backend/ /app
COPY modules/optimize_demo/scripts/ /app/scripts

ENV PYTHONUNBUFFERED=1 OPTIMIZE_PUBLIC_BASE=http://localhost:9320
EXPOSE 9320
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9320"]
