"""Bounded background execution for durable AutoDevelop jobs."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from fastapi.responses import JSONResponse

from autodevelop.jobs.models import JobPhotoResult, JobProgress, JobResult
from autodevelop.jobs.store import JobStore
from autodevelop.models import DevelopRequest, DevelopResponse, ErrorResponse

DevelopProcessor = Callable[
    [DevelopRequest],
    Awaitable[DevelopResponse | JSONResponse],
]


class RetryableJobError(RuntimeError):
    """A photo failed transiently and must not be checkpointed."""


class JobRunner:
    """Run resumable jobs without coupling workers to HTTP transport."""

    def __init__(
        self,
        store: JobStore,
        max_workers: int,
        processor: DevelopProcessor,
        logger: logging.Logger,
    ) -> None:
        self.store = store
        self.processor = processor
        self.logger = logger
        self.executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers),
            thread_name_prefix="autodevelop-job",
        )
        self._active: set[str] = set()
        self._lock = Lock()

    def queue(self, job_id: str) -> dict[str, object]:
        self.store.require_complete_upload(job_id)
        status = self.store.get_status(job_id)
        if status.get("status") == "completed":
            return {
                "job_id": job_id,
                "status": "completed",
                "already_running": False,
                "resumed": False,
            }
        with self._lock:
            if job_id in self._active:
                return {
                    "job_id": job_id,
                    "status": "running",
                    "already_running": True,
                    "resumed": False,
                }
            self._active.add(job_id)

        request = self.store.get_request(job_id)
        checkpoint = self.store.load_checkpoint(job_id)
        progress = JobProgress(
            stage="queued",
            processed_photos=len(checkpoint),
            total_photos=len(request.photos),
        )
        try:
            self.store.set_status(job_id, "running", progress, errors=[])
            self.executor.submit(self._run, job_id)
        except Exception:
            with self._lock:
                self._active.discard(job_id)
            self.store.set_status(
                job_id,
                "failed",
                progress,
                errors=["The job could not be queued."],
                resumable=True,
            )
            raise
        return {
            "job_id": job_id,
            "status": "running",
            "already_running": False,
            "resumed": status.get("status") in {"failed", "interrupted"},
        }

    def _run(self, job_id: str) -> None:
        try:
            self.process(job_id)
        except RetryableJobError as exc:
            self.logger.warning("job_retryable_failure job_id=%s code=%s", job_id, exc)
            self._mark_failed(job_id, str(exc))
        except Exception:
            self.logger.exception("job_failed job_id=%s", job_id)
            self._mark_failed(job_id, "unexpected_processing_failure")
        finally:
            with self._lock:
                self._active.discard(job_id)

    def _mark_failed(self, job_id: str, error_code: str) -> None:
        try:
            status = self.store.get_status(job_id)
            self.store.set_status(
                job_id,
                "failed",
                JobProgress.model_validate(status.get("progress", {})),
                errors=[error_code],
                resumable=True,
            )
        except Exception:
            self.logger.exception("job_failure_status_write_failed job_id=%s", job_id)

    def process(self, job_id: str) -> None:
        request = self.store.get_request(job_id)
        completed = self.store.load_checkpoint(job_id)
        total = len(request.photos)
        for photo in request.photos:
            if photo.photo_id in completed:
                continue
            self.store.set_status(
                job_id,
                "running",
                JobProgress(
                    stage="generating",
                    processed_photos=len(completed),
                    total_photos=total,
                    current_photo_id=photo.photo_id,
                ),
                errors=[],
            )
            develop_request = photo.build_request(
                self.store.load_preview_base64(job_id, photo.photo_id)
            )
            outcome = asyncio.run(self.processor(develop_request))
            result = self._checkpoint_result(photo.photo_id, outcome)
            self.store.save_checkpoint(job_id, result)
            completed[photo.photo_id] = result
            self.store.set_status(
                job_id,
                "running",
                JobProgress(
                    stage="generating",
                    processed_photos=len(completed),
                    total_photos=total,
                ),
                errors=[],
            )

        ordered = [completed[photo.photo_id] for photo in request.photos]
        succeeded = sum(
            isinstance(item.response, DevelopResponse) for item in ordered
        )
        self.store.save_result(
            JobResult(
                job_id=job_id,
                results=ordered,
                succeeded_photos=succeeded,
                failed_photos=total - succeeded,
            )
        )
        self.store.set_status(
            job_id,
            "completed",
            JobProgress(
                stage="completed",
                processed_photos=total,
                total_photos=total,
            ),
            errors=[],
            resumable=False,
        )
        self.logger.info(
            "job_completed job_id=%s photos=%d succeeded=%d failed=%d",
            job_id,
            total,
            succeeded,
            total - succeeded,
        )

    @staticmethod
    def _checkpoint_result(
        photo_id: str,
        outcome: DevelopResponse | JSONResponse,
    ) -> JobPhotoResult:
        if isinstance(outcome, DevelopResponse):
            return JobPhotoResult(
                photo_id=photo_id,
                http_status=200,
                response=outcome,
            )
        payload = json.loads(outcome.body)
        error = ErrorResponse.model_validate(payload)
        if error.error.retryable:
            raise RetryableJobError(error.error.code)
        return JobPhotoResult(
            photo_id=photo_id,
            http_status=outcome.status_code,
            response=error,
        )

    def shutdown(self) -> None:
        """Reject queued work while allowing an active checkpoint to finish."""

        self.executor.shutdown(wait=False, cancel_futures=True)
