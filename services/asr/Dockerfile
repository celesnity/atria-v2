# CPU-only ASR sidecar for nvidia/nemotron-3.5-asr-streaming-0.6b.
# Kept OUT of the main atria image (python:3.12-slim) on purpose: torch +
# transformers + model weights would bloat it and are only needed here.
FROM python:3.11-slim

# ffmpeg + libsndfile back the audio decode/resample (librosa/soundfile);
# git is needed to install transformers from source (see below).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch CPU wheel from the pytorch CPU index (avoids the multi-GB CUDA build).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ENV ASR_MODEL=nvidia/nemotron-3.5-asr-streaming-0.6b
ENV HF_HOME=/models
ENV PYTHONUNBUFFERED=1

# Pre-download the model weights at build time (needs only huggingface_hub,
# pulled in via accelerate) so the container is offline-safe and the first
# request isn't a cold multi-hundred-MB download. Done BEFORE the volatile
# source install so this heavy layer stays cached across code tweaks. Non-fatal
# if the build host has no network — the model is fetched lazily on first use.
RUN python -c "from huggingface_hub import snapshot_download; import os; snapshot_download(os.environ['ASR_MODEL'])" || \
    echo "[asr] model pre-download skipped (no network at build) — will fetch on first request"

# nemotron-3.5-asr uses a very new architecture (`nemotron3_5_asr`) that is not
# in any released transformers yet, so install from source per the model card.
RUN pip install --no-cache-dir "git+https://github.com/huggingface/transformers.git"

COPY app.py ./

EXPOSE 9000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
