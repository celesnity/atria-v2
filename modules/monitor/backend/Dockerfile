# Monitor connector image (BACKEND ONLY — no Module-Federation frontend this pass; the tile stays the
# vanilla dashboard.html served by Core). Build context is the REPO ROOT so the image can install the
# shared minder_python_sdk from the repo root:
#   docker compose ... up -d --build monitor
FROM python:3.12-slim
WORKDIR /app

# Shared connector SDK first (own layer, rarely changes).
COPY minder_python_sdk /sdk
RUN pip install --no-cache-dir /sdk

# Module's own (light) deps.
COPY modules/monitor/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Connector code + the reused fleet logic. service.py adds ./scripts to sys.path in-container.
COPY modules/monitor/backend/ /app
COPY modules/monitor/scripts/ /app/scripts

ENV PYTHONUNBUFFERED=1 MONITOR_PUBLIC_BASE=http://localhost:9310
EXPOSE 9310
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9310"]
