"""Produce worker entrypoint — imports the backend task module so `celery -A tasks`
resolves. The worker Dockerfile sets WORKDIR to the backend code tree, so this
file is only used when running the worker from the module root."""

from __future__ import annotations

from celery_app import celery_app  # noqa: F401
from tasks import oee_snapshot  # noqa: F401
