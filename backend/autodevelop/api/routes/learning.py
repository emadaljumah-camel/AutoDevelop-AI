"""Safe local-learning API endpoints."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from autodevelop.api.dependencies import get_learning_service
from autodevelop.learning import (
    BaselineConflictError,
    BaselineRequest,
    BaselineResponse,
    DeleteAllLearningRequest,
    FeedbackPreviewResponse,
    FeedbackRequest,
    FeedbackResponse,
    LearningSessionNotFoundError,
    LearningStatusResponse,
    PhotoKeyMismatchError,
)
from autodevelop.learning.schemas import DeleteLearningResponse
from autodevelop.learning.service import (
    LearningBaselineUnavailableError,
    LearningModelError,
    LearningPayloadTooLargeError,
    LearningProfileError,
    LearningService,
    LearningUnavailableError,
)

router = APIRouter(prefix="/learning", tags=["learning"])
logger = logging.getLogger(__name__)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "schema_version": 1,
            "error": {"code": code, "message": message},
        },
    )


@router.post("/baselines", response_model=BaselineResponse)
async def store_baseline(
    request: BaselineRequest,
    service: Annotated[LearningService, Depends(get_learning_service)],
) -> BaselineResponse | JSONResponse:
    try:
        return await service.store_baseline(request)
    except BaselineConflictError:
        return _error(409, "baseline_conflict", "The session ID is already in use.")
    except LearningProfileError:
        return _error(400, "profile_not_found", "The style profile is unavailable.")
    except LearningModelError:
        return _error(400, "model_unavailable", "The model is unavailable.")
    except LearningPayloadTooLargeError:
        return _error(413, "payload_too_large", "The learning payload is too large.")
    except LearningUnavailableError:
        return _error(503, "learning_unavailable", "Learning storage is unavailable.")
@router.post("/feedback", response_model=FeedbackResponse)
async def capture_feedback(
    request: FeedbackRequest,
    service: Annotated[LearningService, Depends(get_learning_service)],
) -> FeedbackResponse | JSONResponse:
    try:
        return await service.capture_feedback(request)
    except LearningSessionNotFoundError:
        return _error(404, "session_not_found", "The learning session was not found.")
    except PhotoKeyMismatchError:
        return _error(409, "photo_key_mismatch", "The selected photo does not match.")
    except LearningBaselineUnavailableError:
        return _error(
            409,
            "baseline_unavailable",
            "Capture a new Auto Develop baseline before saving feedback.",
        )
    except LearningPayloadTooLargeError:
        return _error(413, "payload_too_large", "The learning payload is too large.")
    except LearningUnavailableError:
        return _error(503, "learning_unavailable", "Learning storage is unavailable.")
    except ValidationError:
        logger.exception("learning_feedback_schema_error")
        return _error(
            500,
            "feedback_processing_error",
            "Feedback could not be processed safely.",
        )


@router.post("/feedback/preview", response_model=FeedbackPreviewResponse)
async def preview_feedback(
    request: FeedbackRequest,
    service: Annotated[LearningService, Depends(get_learning_service)],
) -> FeedbackPreviewResponse | JSONResponse:
    try:
        return await service.preview_feedback(request)
    except LearningSessionNotFoundError:
        return _error(404, "session_not_found", "The learning session was not found.")
    except PhotoKeyMismatchError:
        return _error(409, "photo_key_mismatch", "The selected photo does not match.")
    except LearningBaselineUnavailableError:
        return _error(
            409,
            "baseline_unavailable",
            "Capture a new Auto Develop baseline before saving feedback.",
        )
    except LearningPayloadTooLargeError:
        return _error(413, "payload_too_large", "The learning payload is too large.")
    except LearningUnavailableError:
        return _error(503, "learning_unavailable", "Learning storage is unavailable.")
    except ValidationError:
        logger.exception("learning_feedback_preview_schema_error")
        return _error(
            500,
            "feedback_processing_error",
            "Feedback could not be processed safely.",
        )


@router.get("/status", response_model=LearningStatusResponse)
async def learning_status(
    service: Annotated[LearningService, Depends(get_learning_service)],
) -> LearningStatusResponse:
    return await service.status()


@router.delete(
    "/sessions/{session_id}",
    response_model=DeleteLearningResponse,
)
async def delete_session(
    session_id: UUID,
    service: Annotated[LearningService, Depends(get_learning_service)],
) -> DeleteLearningResponse | JSONResponse:
    try:
        deleted = await service.dismiss(session_id)
    except LearningUnavailableError:
        return _error(503, "learning_unavailable", "Learning storage is unavailable.")
    if not deleted:
        return _error(404, "session_not_found", "The learning session was not found.")
    return DeleteLearningResponse(deleted=True, affected_sessions=1)


@router.delete("/all", response_model=DeleteLearningResponse)
async def delete_all_learning(
    request: DeleteAllLearningRequest,
    service: Annotated[LearningService, Depends(get_learning_service)],
) -> DeleteLearningResponse | JSONResponse:
    try:
        count = await service.delete_all()
    except LearningUnavailableError:
        return _error(503, "learning_unavailable", "Learning storage is unavailable.")
    return DeleteLearningResponse(deleted=True, affected_sessions=count)
