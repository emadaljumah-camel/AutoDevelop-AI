"""Tests for durable job validation and atomic filesystem storage."""

import base64
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from autodevelop.jobs import (
    CreateDevelopJobRequest,
    JobConflictError,
    JobPhotoResult,
    JobProgress,
    JobResult,
    JobStore,
    PreviewConflictError,
)
from autodevelop.models import ErrorDetail, ErrorResponse

JPEG_ONE = b"\xff\xd8\xffone"
JPEG_TWO = b"\xff\xd8\xfftwo"


def _develop_request(request_id: str, filename: str) -> dict[str, Any]:
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


def _manifest(job_id: str = "client-job-1") -> CreateDevelopJobRequest:
    return CreateDevelopJobRequest.model_validate(
        {
            "client_job_id": job_id,
            "plugin_version": "0.1.0",
            "photos": [
                {
                    "photo_id": "photo-1",
                    "request": _develop_request(
                        "11111111-1111-4111-8111-111111111111",
                        "one.nef",
                    ),
                },
                {
                    "photo_id": "photo-2",
                    "request": _develop_request(
                        "22222222-2222-4222-8222-222222222222",
                        "two.nef",
                    ),
                },
            ],
        }
    )


def _error_result(photo_id: str, request_id: str, filename: str) -> JobPhotoResult:
    return JobPhotoResult(
        photo_id=photo_id,
        http_status=502,
        response=ErrorResponse(
            schema_version="1.0",
            request_id=request_id,
            filename=filename,
            status="error",
            error=ErrorDetail(
                code="model_client_error",
                message="The model service could not complete the request.",
                retryable=False,
            ),
        ),
    )


def test_manifest_normalizes_and_rejects_embedded_previews() -> None:
    manifest = _manifest()
    assert manifest.photos[0].request["request_id"] == (
        "11111111-1111-4111-8111-111111111111"
    )
    assert "preview_base64" not in manifest.photos[0].request
    assert manifest.photos[0].build_request("encoded").preview_base64 == "encoded"

    payload = manifest.model_dump(mode="json")
    payload["photos"][0]["request"]["preview_base64"] = "embedded"
    with pytest.raises(ValidationError, match="must not contain preview"):
        CreateDevelopJobRequest.model_validate(payload)


@pytest.mark.parametrize("identifier", ["../escape", "has space", "", "a/b"])
def test_unsafe_identifiers_are_rejected(identifier: str) -> None:
    payload = _manifest().model_dump(mode="json")
    payload["client_job_id"] = identifier
    with pytest.raises(ValidationError):
        CreateDevelopJobRequest.model_validate(payload)


def test_duplicate_photo_and_request_ids_are_rejected() -> None:
    payload = _manifest().model_dump(mode="json")
    payload["photos"][1]["photo_id"] = "photo-1"
    with pytest.raises(ValidationError, match="unique photo_id"):
        CreateDevelopJobRequest.model_validate(payload)

    payload = _manifest().model_dump(mode="json")
    payload["photos"][1]["request"]["request_id"] = payload["photos"][0][
        "request"
    ]["request_id"]
    with pytest.raises(ValidationError, match="unique request_id"):
        CreateDevelopJobRequest.model_validate(payload)


def test_create_and_preview_upload_are_idempotent(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job_id, reused = store.create_job(_manifest())
    repeated_id, repeated = store.create_job(_manifest())
    digest, upload_reused = store.save_preview(
        job_id,
        "photo-1",
        base64.b64encode(JPEG_ONE).decode("ascii"),
    )
    repeated_digest, repeated_upload = store.save_preview(
        job_id,
        "photo-1",
        base64.b64encode(JPEG_ONE).decode("ascii"),
    )

    assert reused is False
    assert repeated is True
    assert repeated_id == job_id
    assert upload_reused is False
    assert repeated_upload is True
    assert repeated_digest == digest
    assert store.uploaded_photo_ids(job_id) == ["photo-1"]
    assert store.load_preview_base64(job_id, "photo-1") == base64.b64encode(
        JPEG_ONE
    ).decode("ascii")


def test_binary_preview_preserves_bytes_and_matches_legacy_upload(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    preview = JPEG_ONE + b"\x00Exif"
    digest, reused = store.save_preview_bytes(job_id, "photo-1", preview)
    repeated_digest, repeated = store.save_preview(
        job_id,
        "photo-1",
        base64.b64encode(preview).decode("ascii"),
    )

    assert reused is False
    assert repeated is True
    assert repeated_digest == digest
    assert store.preview_path(job_id, "photo-1").read_bytes() == preview


def test_manifest_and_preview_conflicts_are_rejected(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    changed = _manifest().model_copy(deep=True)
    changed.photos[0].request["filename"] = "changed.nef"
    with pytest.raises(JobConflictError):
        store.create_job(changed)

    store.save_preview(
        job_id,
        "photo-1",
        base64.b64encode(JPEG_ONE).decode("ascii"),
    )
    with pytest.raises(PreviewConflictError):
        store.save_preview(
            job_id,
            "photo-1",
            base64.b64encode(JPEG_TWO).decode("ascii"),
        )


@pytest.mark.parametrize(
    "encoded",
    ["not-base64!", base64.b64encode(b"not-jpeg").decode("ascii")],
)
def test_invalid_previews_are_rejected(tmp_path: Path, encoded: str) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    with pytest.raises(ValueError):
        store.save_preview(job_id, "photo-1", encoded)


def test_preview_size_limit_is_enforced(tmp_path: Path) -> None:
    store = JobStore(tmp_path, max_preview_bytes=5)
    job_id, _ = store.create_job(_manifest())
    with pytest.raises(ValueError, match="size limit"):
        store.save_preview(
            job_id,
            "photo-1",
            base64.b64encode(JPEG_ONE).decode("ascii"),
        )


def test_complete_upload_requires_every_manifest_photo(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    store.save_preview(
        job_id,
        "photo-1",
        base64.b64encode(JPEG_ONE).decode("ascii"),
    )
    with pytest.raises(ValueError, match="photo-2"):
        store.require_complete_upload(job_id)


def test_checkpoints_are_idempotent_but_immutable(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    first = _error_result(
        "photo-1",
        "11111111-1111-4111-8111-111111111111",
        "one.nef",
    )
    store.save_checkpoint(job_id, first)
    store.save_checkpoint(job_id, first)
    assert store.load_checkpoint(job_id) == {"photo-1": first}

    changed = first.model_copy(update={"http_status": 500})
    with pytest.raises(JobConflictError):
        store.save_checkpoint(job_id, changed)


def test_final_result_must_follow_manifest_order(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    first = _error_result(
        "photo-1",
        "11111111-1111-4111-8111-111111111111",
        "one.nef",
    )
    second = _error_result(
        "photo-2",
        "22222222-2222-4222-8222-222222222222",
        "two.nef",
    )
    reversed_result = JobResult(
        job_id=job_id,
        results=[second, first],
        succeeded_photos=0,
        failed_photos=2,
    )
    with pytest.raises(ValueError, match="photo order"):
        store.save_result(reversed_result)

    result = reversed_result.model_copy(update={"results": [first, second]})
    store.save_result(result)
    assert store.load_result(job_id) == result


def test_running_job_is_marked_interrupted_after_restart(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job_id, _ = store.create_job(_manifest())
    store.set_status(
        job_id,
        "running",
        JobProgress(stage="generating", total_photos=2),
    )

    assert store.mark_running_jobs_interrupted() == [job_id]
    status = store.get_status(job_id)
    assert status["status"] == "interrupted"
    assert status["resumable"] is True
    assert status["errors"] == ["Server restarted while the job was running"]
    assert status["started_at"] is not None
