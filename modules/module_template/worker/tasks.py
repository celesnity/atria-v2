"""Worker entrypoint module — re-exports the task defined in the backend package.
The worker image sets PYTHONPATH to the backend dir so `import tasks` resolves there."""

from tasks import celery_app, run_job  # noqa: F401
