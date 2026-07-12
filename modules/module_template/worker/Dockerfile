FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY minder_module_sdk /sdk
RUN pip install --no-cache-dir /sdk
COPY modules/module_template/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/module_template/backend/ /app
ENV PYTHONUNBUFFERED=1
# Run Celery as a non-root user (Celery refuses/warns under root by default).
RUN useradd --system --create-home appuser
USER appuser
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]
