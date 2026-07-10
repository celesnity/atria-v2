"""Worker entrypoint re-export (for local `celery -A worker.tasks worker` runs).
The container image instead runs `celery -A tasks worker` from WORKDIR /app (the
backend tree), so this file is not copied into the image — the canonical task lives
in backend/tasks.py."""

from tasks import celery_app, run_job  # noqa: F401
