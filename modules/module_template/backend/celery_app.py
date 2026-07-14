"""module_template Celery app — reuses the shared Redis INSTANCE at DB index /2."""

from __future__ import annotations

import os

from celery import Celery

MT_REDIS_URL = os.environ.get("MT_REDIS_URL", "redis://redis:6379/2")

celery_app = Celery("module_template", broker=MT_REDIS_URL, backend=MT_REDIS_URL, include=["tasks"])
celery_app.conf.update(task_track_started=True, result_expires=3600)
if os.environ.get("MT_TEST") == "1":
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
