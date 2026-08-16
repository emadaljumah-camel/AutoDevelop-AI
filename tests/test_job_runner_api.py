"""Runner checkpoint/resume behavior and asynchronous job API tests."""

import base64
import logging
from pathlib import Path
from typing import Any
from unittest.mock import Mock

from fastapi.testclient import TestClient

from autodevelop.config import Settings
from autodevelop.jobs import (
    CreateDevelopJobRequest,
    JobRunner,
    JobStore,
    RetryableJobError,
)
from autodevelop.main import create_app
from autodevelop.model_clients import FakeModelClient
from autodevelop.models import DevelopRequest, DevelopResponse, ErrorDetail, ErrorResponse

JPEG = b"\xff\xd8\xffjob-preview"


def _request(request_id: str, filename: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_id": request_id,
        "filename": filename,
        "model": "gemma",
        "exif": {"iso": 400, "file_format": "RAW"},
        "current_settings": {},
        "options": {"style_profile": "natural_travel"},
        "learning": {"enabled": True},
    }


def _manifest() -> CreateDevelopJobRequest:
    return CreateDevelopJobRequest.model_validate(
        {
            "client_job_id": "runner-job",
            "plugin_version": "0.1.0",
            "photos": [
                {
                    "photo_id": "photo-1",
                    "request": _request(
                        "11111111-1111-4111-8111-111111111111", "one.nef"
                    ),
                },
                {
                    "photo_id": "photo-2",
                    "request": _request(
                        "22222222-2222-4222-8222-222222222222", "two.nef"
                    ),
                },
            ],
        }
    )


def _success(request: DevelopRequest) -> DevelopResponse:
    return DevelopResponse(
        schema_version="1.0",
        request_id=request.request_id,
        filename=request.filename,
        status="success",
        model=request.model or "gemma",
        resolved_model="gemma-4-31b",
    )


def _upload_all(store: JobStore, job_id: str) -> None:
    encoded = base64.b64encode(JPEG).decode("ascii")
    store.save_preview(job_id, "photo-1", encoded)
    store.save_preview(job_id, "photo-2", encoded)


def test_runner_checkpoints_and_completes_in_manifest_order(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    _upload_all(store, job_id)
    seen: list[str] = []

    async def processor(request: DevelopRequest) -> DevelopResponse:
        seen.append(request.filename)
        assert request.preview_base64 == base64.b64encode(JPEG).decode("ascii")
        return _success(request)

    runner = JobRunner(store, 1, processor, logging.getLogger("job-test"))
    runner.process(job_id)
    runner.shutdown()

    assert seen == ["one.nef", "two.nef"]
    assert list(store.load_checkpoint(job_id)) == ["photo-1", "photo-2"]
    result = store.load_result(job_id)
    assert [item.photo_id for item in result.results] == ["photo-1", "photo-2"]
    assert result.succeeded_photos == 2
    assert result.failed_photos == 0
    assert store.get_status(job_id)["status"] == "completed"


def test_retryable_response_is_not_checkpointed_and_resume_uses_checkpoint(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    _upload_all(store, job_id)
    fail_second = True
    seen: list[str] = []

    async def processor(request: DevelopRequest):
        nonlocal fail_second
        seen.append(request.filename)
        if request.filename == "two.nef" and fail_second:
            return _error_response(request, retryable=True)
        return _success(request)

    runner = JobRunner(store, 1, processor, logging.getLogger("job-test"))
    try:
        runner.process(job_id)
    except RetryableJobError:
        pass
    else:
        raise AssertionError("retryable response did not stop the job")

    assert list(store.load_checkpoint(job_id)) == ["photo-1"]
    fail_second = False
    runner.process(job_id)
    runner.shutdown()
    assert seen == ["one.nef", "two.nef", "two.nef"]
    assert store.get_status(job_id)["status"] == "completed"


def _error_response(request: DevelopRequest, *, retryable: bool):
    from fastapi.responses import JSONResponse

    error = ErrorResponse(
        schema_version="1.0",
        request_id=request.request_id,
        filename=request.filename,
        status="error",
        error=ErrorDetail(
            code="model_client_error",
            message="The model service could not complete the request.",
            retryable=retryable,
        ),
    )
    return JSONResponse(
        status_code=502,
        content=error.model_dump(mode="json"),
    )


def test_nonretryable_response_is_checkpointed_and_batch_completes(
    tmp_path: Path,
) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    _upload_all(store, job_id)

    async def processor(request: DevelopRequest):
        if request.filename == "one.nef":
            return _error_response(request, retryable=False)
        return _success(request)

    runner = JobRunner(store, 1, processor, logging.getLogger("job-test"))
    runner.process(job_id)
    runner.shutdown()
    result = store.load_result(job_id)
    assert result.succeeded_photos == 1
    assert result.failed_photos == 1


def test_job_api_create_upload_queue_status_and_not_found(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    runner = Mock()
    runner.queue.return_value = {
        "job_id": "runner-job",
        "status": "running",
        "already_running": False,
        "resumed": False,
    }
    app = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "autodevelop.log",
            jobs_dir=tmp_path / "jobs",
        ),
        model_client=FakeModelClient(),
        job_store=store,
        job_runner=runner,
    )

    with TestClient(app) as client:
        created = client.post(
            "/autodevelop/v1/jobs",
            json=_manifest().model_dump(mode="json"),
        )
        uploaded = client.post(
            "/autodevelop/v1/jobs/runner-job/photos/photo-1/preview",
            json={"image_base64": base64.b64encode(JPEG).decode("ascii")},
        )
        uploads = client.get("/autodevelop/v1/jobs/runner-job/uploads")
        queued = client.post("/autodevelop/v1/jobs/runner-job/run")
        status = client.get("/autodevelop/v1/jobs/runner-job/status")
        missing = client.get("/autodevelop/v1/jobs/not-present/status")

    assert created.status_code == 200
    assert created.json()["reused"] is False
    assert uploaded.status_code == 200
    assert uploads.json()["uploaded_photo_ids"] == ["photo-1"]
    assert queued.status_code == 200
    assert status.json()["status"] == "created"
    assert missing.status_code == 404
    runner.queue.assert_called_once_with("runner-job")
    runner.shutdown.assert_called_once_with()
