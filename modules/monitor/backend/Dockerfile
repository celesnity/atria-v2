# Build context is the repository root.

FROM node:20-slim AS frontend
WORKDIR /frontend
COPY modules/monitor/frontend/package.json modules/monitor/frontend/package-lock.json* ./
RUN npm ci
COPY modules/monitor/frontend/ ./
COPY minder_ui_sdk /minder_ui_sdk
ARG MONITOR_PUBLIC_BASE=http://localhost:9310
ENV MONITOR_PUBLIC_BASE=$MONITOR_PUBLIC_BASE
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY minder_python_sdk /sdk
RUN pip install --no-cache-dir /sdk
COPY modules/monitor/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/monitor/backend/ /app
COPY modules/monitor/scripts/ /app/scripts
COPY --from=frontend /frontend/dist /app/frontend_dist

ENV PYTHONUNBUFFERED=1 \
    MONITOR_PUBLIC_BASE=http://localhost:9310 \
    MONITOR_DASHBOARD_DIST=/app/frontend_dist
EXPOSE 9310
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9310"]
