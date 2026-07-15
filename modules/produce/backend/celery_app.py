"""Produce Celery app — reuses the shared Redis INSTANCE at DB index /3."""

from __future__ import annotations

import os

from celery import Celery

PR_REDIS_URL = os.environ.get("PR_REDIS_URL", "redis://redis:6379/3")

celery_app = Celery("produce", broker=PR_REDIS_URL, backend=PR_REDIS_URL, include=["tasks"])
celery_app.conf.update(task_track_started=True, result_expires=3600)
if os.environ.get("PR_TEST") == "1":
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
