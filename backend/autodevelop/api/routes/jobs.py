"""Durable asynchronous AutoDevelop job endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from autodevelop.api.dependencies import get_job_runner, get_job_store
from autodevelop.jobs import (
    CreateDevelopJobRequest,
    JobConflictError,
    JobRunner,
    JobStore,
    PreviewConflictError,
    PreviewUploadRequest,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _require_job(job_id: str, store: JobStore) -> None:
    try:
        exists = store.exists(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown job") from exc
    if not exists:
        raise HTTPException(status_code=404, detail="Unknown job")


@router.post("")
def create_job(
    request: CreateDevelopJobRequest,
    store: Annotated[JobStore, Depends(get_job_store)],
) -> dict[str, object]:
    try:
        job_id, reused = store.create_job(request)
    except (JobConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "job_id": job_id,
        "status": store.get_status(job_id)["status"],
        "reused": reused,
    }


@router.post("/{job_id}/photos/{photo_id}/preview")
def upload_job_preview(
    job_id: str,
    photo_id: str,
    request: PreviewUploadRequest,
    store: Annotated[JobStore, Depends(get_job_store)],
) -> dict[str, object]:
    _require_job(job_id, store)
    try:
        digest, reused = store.save_preview(job_id, photo_id, request.image_base64)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Unknown photo_id for this job",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PreviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "job_id": job_id,
        "photo_id": photo_id,
        "sha256": digest,
        "reused": reused,
    }


@router.get("/{job_id}/uploads")
def uploaded_job_photos(
    job_id: str,
    store: Annotated[JobStore, Depends(get_job_store)],
) -> dict[str, object]:
    _require_job(job_id, store)
    return {
        "job_id": job_id,
        "uploaded_photo_ids": store.uploaded_photo_ids(job_id),
    }


@router.post("/{job_id}/run")
def run_job(
    job_id: str,
    store: Annotated[JobStore, Depends(get_job_store)],
    runner: Annotated[JobRunner, Depends(get_job_runner)],
) -> dict[str, object]:
    _require_job(job_id, store)
    try:
        return runner.queue(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{job_id}/status")
def job_status(
    job_id: str,
    store: Annotated[JobStore, Depends(get_job_store)],
) -> dict[str, object]:
    _require_job(job_id, store)
    return store.get_status(job_id)


@router.get("/{job_id}/result")
def job_result(
    job_id: str,
    store: Annotated[JobStore, Depends(get_job_store)],
) -> dict[str, object]:
    _require_job(job_id, store)
    status = store.get_status(job_id)
    if status.get("status") != "completed":
        return status
    try:
        return store.load_result(job_id).model_dump(mode="json")
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Stored job result is invalid",
        ) from exc
