# Build context is the REPO ROOT (shared minder_ui_sdk lives outside the module).

# --- frontend build stage ---
FROM node:20-slim AS fe
WORKDIR /fe
COPY modules/produce/frontend/package.json modules/produce/frontend/package-lock.json* ./
RUN npm install
COPY modules/produce/frontend/ ./
COPY minder_ui_sdk /minder_ui_sdk
ARG PR_PUBLIC_BASE=http://localhost:9310
ENV PR_PUBLIC_BASE=$PR_PUBLIC_BASE
RUN npm run build

# --- python service stage ---
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY modules/produce/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/produce/backend/ /app
COPY --from=fe /fe/dist /app/frontend_dist
ENV PYTHONUNBUFFERED=1
RUN useradd --system --create-home appuser
USER appuser
EXPOSE 9310
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9310"]
