# Standalone maintenance_copilot RAG service. Kept OUT of the main atria image:
# openai/qdrant-client/neo4j/chonkie + the pipeline only run here.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# pipeline/, sample_manuals/, service.py, app.py
COPY . /app

ENV PYTHONUNBUFFERED=1 \
    MC_PUBLIC_BASE=http://localhost:9200

EXPOSE 9200

# service.py puts pipeline/ on sys.path at import; run from /app so `import service`
# and `import app` resolve.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9200"]
