"""ResearchJob dataclass and singleton job manager."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ResearchJob:
    job_id: str
    topic: str
    depth: str
    taxonomy: Dict[str, Any]
    status: str = "queued"
    progress: float = 0.0
    report_sections: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class JobManager:
    _instance: Optional["JobManager"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._jobs: Dict[str, ResearchJob] = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="deep_research")

    @classmethod
    def instance(cls) -> "JobManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def submit(self, job: ResearchJob, fn: Callable[[ResearchJob], None]) -> None:
        self._jobs[job.job_id] = job
        self._executor.submit(fn, job)

    def get(self, job_id: str) -> Optional[ResearchJob]:
        return self._jobs.get(job_id)
