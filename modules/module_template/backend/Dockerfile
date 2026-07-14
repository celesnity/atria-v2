# Build context is the REPO ROOT so the image can install the shared minder-python-sdk.

# --- frontend build stage ---
FROM node:20-slim AS fe
WORKDIR /fe
COPY modules/module_template/frontend/package.json modules/module_template/frontend/package-lock.json* ./
RUN npm install
COPY modules/module_template/frontend/ ./
# minder-ui-sdk is consumed from source via a vite alias (../../../minder_ui_sdk).
COPY minder_ui_sdk /minder_ui_sdk
RUN npm run build

# --- python service stage ---
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY minder_python_sdk /sdk
RUN pip install --no-cache-dir /sdk
COPY modules/module_template/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/module_template/backend/ /app
COPY --from=fe /fe/dist /app/frontend_dist
ENV PYTHONUNBUFFERED=1 MT_PUBLIC_BASE=http://localhost:9300
# Run as a non-root user (the app writes to Postgres/S3, not the local FS).
RUN useradd --system --create-home appuser
USER appuser
EXPOSE 9300
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9300"]
