"""Normalize legacy and explicit model selection at the API boundary."""

from dataclasses import dataclass
from typing import Literal

from autodevelop.config import Settings
from autodevelop.model_clients.exceptions import ModelRequestError
from autodevelop.model_clients.resolver import ModelResolver, ResolvedModel
from autodevelop.models import AnalyzeRequest, DevelopRequest

ModelSource = Literal["explicit", "default"]


@dataclass(frozen=True)
class ModelSelection:
    """One normalized request and its validated model resolution."""

    request: AnalyzeRequest | DevelopRequest
    resolution: ResolvedModel
    source: ModelSource


def resolve_model_request(
    request: AnalyzeRequest | DevelopRequest,
    *,
    settings: Settings,
    resolver: ModelResolver,
) -> ModelSelection:
    """Return a copied request with one explicit, normally resolved model."""

    if "model" not in request.model_fields_set:
        source: ModelSource = "default"
        effective_model = settings.default_model
    elif request.model is None:
        raise ModelRequestError(
            "An explicitly null model selection is invalid.",
            model_name="unresolved",
        )
    else:
        source = "explicit"
        effective_model = request.model
    resolution = resolver.resolve(effective_model)
    normalized = request.model_copy(update={"model": effective_model}, deep=True)
    return ModelSelection(
        request=normalized,
        resolution=resolution,
        source=source,
    )
