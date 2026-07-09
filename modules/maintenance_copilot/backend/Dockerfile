# --- frontend build stage ---
FROM node:20-slim AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- python service stage ---
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app
COPY --from=fe /fe/dist /app/frontend_dist
ENV PYTHONUNBUFFERED=1 \
    MC_PUBLIC_BASE=http://localhost:9200
EXPOSE 9200
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9200"]
