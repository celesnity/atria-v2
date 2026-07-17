FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY modules/produce/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/produce/backend/ /app
ENV PYTHONUNBUFFERED=1
RUN useradd --system --create-home appuser
USER appuser
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]
