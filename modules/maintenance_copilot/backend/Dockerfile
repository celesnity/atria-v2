# Build context is the REPO ROOT (see docker-compose.yml) so the image can install
# the shared atria-module-sdk, which lives at the repo root.

# --- frontend build stage ---
FROM node:20-slim AS fe
WORKDIR /fe
COPY modules/maintenance_copilot/frontend/package.json modules/maintenance_copilot/frontend/package-lock.json* ./
RUN npm install
COPY modules/maintenance_copilot/frontend/ ./
RUN npm run build

# --- python service stage ---
FROM python:3.12-slim
WORKDIR /app

# Install the shared connector SDK first (own layer, rarely changes).
COPY atria_module_sdk /sdk
RUN pip install --no-cache-dir /sdk

# Module's own heavy deps.
COPY modules/maintenance_copilot/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY modules/maintenance_copilot/backend/ /app
COPY --from=fe /fe/dist /app/frontend_dist
ENV PYTHONUNBUFFERED=1 \
    MC_PUBLIC_BASE=http://localhost:9200
EXPOSE 9200
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9200"]
