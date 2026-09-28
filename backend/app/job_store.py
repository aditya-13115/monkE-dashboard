from __future__ import annotations

import secrets
import threading
import time
from typing import Any


class JobStore:
    """Small in-memory job registry for the single-process prototype."""

    def __init__(self, *, max_jobs: int = 200) -> None:
        self.max_jobs = max_jobs
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active: dict[tuple[str, str], str] = {}

    def create(self, campaign_id: str, kind: str) -> dict[str, Any]:
        with self._lock:
            key = (campaign_id, kind)
            active_id = self._active.get(key)
            if active_id and self._jobs.get(active_id, {}).get("status") in {"queued", "running"}:
                return dict(self._jobs[active_id])

            job_id = f"{kind[:4]}_{secrets.token_urlsafe(9)}"
            job = {
                "jobId": job_id,
                "campaignId": campaign_id,
                "kind": kind,
                "status": "queued",
                "phase": "queued",
                "processed": 0,
                "total": 0,
                "percent": 0.0,
                "message": "Queued",
                "startedAt": None,
                "updatedAt": time.time(),
                "finishedAt": None,
                "error": None,
                "result": None,
            }
            self._jobs[job_id] = job
            self._active[key] = job_id
            self._prune_locked()
            return dict(job)

    def active(self, campaign_id: str, kind: str) -> dict[str, Any] | None:
        with self._lock:
            job_id = self._active.get((campaign_id, kind))
            if not job_id:
                return None
            job = self._jobs.get(job_id)
            if not job or job.get("status") not in {"queued", "running"}:
                return None
            return dict(job)

    def update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {}
            job.update(changes)
            job["updatedAt"] = time.time()
            if job.get("total"):
                job["percent"] = round(
                    min(100.0, max(0.0, float(job.get("processed", 0)) / float(job["total"]) * 100)),
                    1,
                )
            return dict(job)

    def start(self, job_id: str, *, total: int, phase: str, message: str) -> dict[str, Any]:
        return self.update(
            job_id,
            status="running",
            phase=phase,
            total=total,
            processed=0,
            percent=0.0,
            message=message,
            startedAt=time.time(),
            error=None,
        )

    def progress(self, job_id: str, processed: int, *, phase: str | None = None, message: str | None = None) -> dict[str, Any]:
        changes: dict[str, Any] = {"processed": processed}
        if phase is not None:
            changes["phase"] = phase
        if message is not None:
            changes["message"] = message
        return self.update(job_id, **changes)

    def complete(self, job_id: str, *, result: Any = None, message: str = "Complete") -> dict[str, Any]:
        with self._lock:
            current = self._jobs.get(job_id, {})
            total = int(current.get("total", 0) or 0)
        return self.update(
            job_id,
            status="complete",
            phase="complete",
            processed=total,
            percent=100.0,
            message=message,
            result=result,
            finishedAt=time.time(),
        )

    def fail(self, job_id: str, error: str) -> dict[str, Any]:
        return self.update(
            job_id,
            status="failed",
            phase="failed",
            message="Job failed",
            error=error,
            finishedAt=time.time(),
        )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def finish_active(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            key = (str(job["campaignId"]), str(job["kind"]))
            if self._active.get(key) == job_id:
                self._active.pop(key, None)

    def _prune_locked(self) -> None:
        if len(self._jobs) <= self.max_jobs:
            return
        finished = [
            (job_id, float(job.get("finishedAt") or job.get("updatedAt") or 0))
            for job_id, job in self._jobs.items()
            if job.get("status") in {"complete", "failed"}
        ]
        finished.sort(key=lambda item: item[1])
        while len(self._jobs) > self.max_jobs and finished:
            job_id, _ = finished.pop(0)
            self._jobs.pop(job_id, None)
