"""Deterministic fake vision-model client for development and tests."""

from autodevelop.model_clients.base import ModelClient
from autodevelop.model_clients.exceptions import ModelResponseError
from autodevelop.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    CropRecommendation,
    DenoiseRecommendation,
    DevelopRequest,
    DevelopResponse,
    DevelopSettings,
    EditPlan,
    LevelingRecommendation,
    TechnicalAnalysis,
)
from autodevelop.profiles import SceneSignals, StyleProfile, select_style

_SUPPORTED_SCENARIOS = frozenset(
    {
        "auto",
        "neutral",
        "underexposed",
        "overexposed",
        "high_iso",
        "night",
        "landscape",
        "portrait",
        "architecture",
        "documentary",
        "invalid_output",
    }
)

_FILENAME_SCENARIOS = (
    "night",
    "portrait",
    "landscape",
    "architecture",
    "documentary",
    "underexposed",
    "overexposed",
)

_ANALYSIS_DATA: dict[str, dict[str, object]] = {
    "neutral": {
        "scene_type": "general",
        "main_subject": "general scene",
        "lighting": "even light",
        "exposure_assessment": "balanced",
        "white_balance_assessment": "neutral",
        "dynamic_range": "moderate",
        "noise_level": "low",
        "horizon_status": "level",
        "visible_people": 0,
        "has_faces": False,
        "has_sky": False,
        "confidence": 0.95,
    },
    "underexposed": {
        "scene_type": "general",
        "main_subject": "shadowed scene",
        "lighting": "dim",
        "exposure_assessment": "underexposed",
        "white_balance_assessment": "neutral",
        "dynamic_range": "moderate",
        "noise_level": "moderate",
        "horizon_status": "level",
        "visible_people": 0,
        "has_faces": False,
        "has_sky": False,
        "confidence": 0.90,
    },
    "overexposed": {
        "scene_type": "general",
        "main_subject": "bright scene",
        "lighting": "bright",
        "exposure_assessment": "overexposed",
        "white_balance_assessment": "neutral",
        "dynamic_range": "high",
        "noise_level": "low",
        "horizon_status": "level",
        "visible_people": 0,
        "has_faces": False,
        "has_sky": True,
        "confidence": 0.90,
    },
    "high_iso": {
        "scene_type": "general",
        "main_subject": "low-light subject",
        "lighting": "low light",
        "exposure_assessment": "balanced",
        "white_balance_assessment": "neutral",
        "dynamic_range": "moderate",
        "noise_level": "high",
        "horizon_status": "level",
        "visible_people": 0,
        "has_faces": False,
        "has_sky": False,
        "confidence": 0.95,
    },
    "night": {
        "scene_type": "night",
        "main_subject": "night scene",
        "lighting": "low light",
        "exposure_assessment": "highlights require protection",
        "white_balance_assessment": "mixed artificial light",
        "dynamic_range": "high",
        "noise_level": "moderate",
        "horizon_status": "level",
        "visible_people": 0,
        "has_faces": False,
        "has_sky": True,
        "confidence": 0.90,
    },
    "landscape": {
        "scene_type": "landscape",
        "main_subject": "landscape",
        "lighting": "natural light",
        "exposure_assessment": "balanced",
        "white_balance_assessment": "natural",
        "dynamic_range": "high",
        "noise_level": "low",
        "horizon_status": "minor correction may be useful",
        "visible_people": 0,
        "has_faces": False,
        "has_sky": True,
        "confidence": 0.92,
    },
    "portrait": {
        "scene_type": "portrait",
        "main_subject": "person",
        "lighting": "soft subject light",
        "exposure_assessment": "balanced",
        "white_balance_assessment": "natural skin tone",
        "dynamic_range": "moderate",
        "noise_level": "low",
        "horizon_status": "not applicable",
        "visible_people": 1,
        "has_faces": True,
        "has_sky": False,
        "confidence": 0.92,
    },
    "architecture": {
        "scene_type": "architecture",
        "main_subject": "building",
        "lighting": "natural light",
        "exposure_assessment": "bright highlights require control",
        "white_balance_assessment": "neutral",
        "dynamic_range": "high",
        "noise_level": "low",
        "horizon_status": "minor correction may be useful",
        "visible_people": 0,
        "has_faces": False,
        "has_sky": True,
        "confidence": 0.90,
    },
    "documentary": {
        "scene_type": "documentary",
        "main_subject": "candid people",
        "lighting": "available light",
        "exposure_assessment": "balanced",
        "white_balance_assessment": "authentic",
        "dynamic_range": "moderate",
        "noise_level": "low",
        "horizon_status": "level",
        "visible_people": 2,
        "has_faces": True,
        "has_sky": False,
        "confidence": 0.91,
    },
}

_PLAN_DATA: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "neutral": (
        ("Maintain balanced tone", "Keep color natural"),
        ("Avoid unnecessary contrast",),
    ),
    "underexposed": (
        ("Restore exposure", "Recover shadow detail"),
        ("Avoid lifting noise excessively",),
    ),
    "overexposed": (
        ("Recover highlight detail", "Reduce excessive brightness"),
        ("Avoid flattening midtone contrast",),
    ),
    "high_iso": (
        ("Control visible noise", "Preserve important detail"),
        ("Avoid excessive texture enhancement",),
    ),
    "night": (
        ("Protect bright lights", "Recover shadows carefully"),
        ("Avoid excessive shadow lifting",),
    ),
    "landscape": (
        ("Add modest depth", "Enrich natural color"),
        ("Avoid artificial HDR appearance",),
    ),
    "portrait": (
        ("Preserve natural skin", "Keep facial detail gentle"),
        ("Avoid harsh clarity or saturation",),
    ),
    "architecture": (
        ("Control highlights", "Enhance structural detail"),
        (
            "Keep composition cropping conservative",
            "Apply rotational leveling only when a reliable reference supports it",
        ),
    ),
    "documentary": (
        ("Preserve atmosphere", "Maintain authentic color"),
        ("Avoid dramatic color grading",),
    ),
}

_DEVELOP_SETTINGS: dict[str, dict[str, float]] = {
    "neutral": {
        "Exposure2012": 0.0,
        "Contrast2012": 0.0,
        "Highlights2012": -5.0,
        "Shadows2012": 5.0,
        "Whites2012": 0.0,
        "Blacks2012": 0.0,
        "Texture": 0.0,
        "Clarity2012": 0.0,
        "Dehaze": 0.0,
        "Vibrance": 3.0,
        "Saturation": 0.0,
    },
    "underexposed": {
        "Exposure2012": 0.65,
        "Contrast2012": 5.0,
        "Highlights2012": -15.0,
        "Shadows2012": 35.0,
        "Whites2012": 8.0,
        "Blacks2012": -8.0,
        "Texture": 5.0,
        "Clarity2012": 3.0,
        "Dehaze": 2.0,
        "Vibrance": 8.0,
        "Saturation": 0.0,
    },
    "overexposed": {
        "Exposure2012": -0.45,
        "Contrast2012": 3.0,
        "Highlights2012": -45.0,
        "Shadows2012": 10.0,
        "Whites2012": -15.0,
        "Blacks2012": -3.0,
        "Texture": 3.0,
        "Clarity2012": 2.0,
        "Dehaze": 2.0,
        "Vibrance": 5.0,
        "Saturation": 0.0,
    },
    "high_iso": {
        "Exposure2012": 0.15,
        "Contrast2012": 0.0,
        "Highlights2012": -20.0,
        "Shadows2012": 20.0,
        "Whites2012": 0.0,
        "Blacks2012": -5.0,
        "Texture": -5.0,
        "Clarity2012": -3.0,
        "Dehaze": 0.0,
        "Vibrance": 3.0,
        "Saturation": 0.0,
    },
    "night": {
        "Exposure2012": 0.25,
        "Contrast2012": 8.0,
        "Highlights2012": -35.0,
        "Shadows2012": 22.0,
        "Whites2012": -8.0,
        "Blacks2012": -12.0,
        "Texture": 0.0,
        "Clarity2012": 2.0,
        "Dehaze": 4.0,
        "Vibrance": 7.0,
        "Saturation": 0.0,
    },
    "landscape": {
        "Exposure2012": 0.10,
        "Contrast2012": 12.0,
        "Highlights2012": -30.0,
        "Shadows2012": 20.0,
        "Whites2012": 8.0,
        "Blacks2012": -10.0,
        "Texture": 12.0,
        "Clarity2012": 8.0,
        "Dehaze": 7.0,
        "Vibrance": 14.0,
        "Saturation": 2.0,
    },
    "portrait": {
        "Exposure2012": 0.15,
        "Contrast2012": -2.0,
        "Highlights2012": -18.0,
        "Shadows2012": 18.0,
        "Whites2012": 2.0,
        "Blacks2012": -3.0,
        "Texture": -8.0,
        "Clarity2012": -6.0,
        "Dehaze": 0.0,
        "Vibrance": 5.0,
        "Saturation": -2.0,
    },
    "architecture": {
        "Exposure2012": 0.05,
        "Contrast2012": 10.0,
        "Highlights2012": -35.0,
        "Shadows2012": 18.0,
        "Whites2012": 5.0,
        "Blacks2012": -8.0,
        "Texture": 15.0,
        "Clarity2012": 10.0,
        "Dehaze": 5.0,
        "Vibrance": 5.0,
        "Saturation": -1.0,
    },
}

_DEVELOP_SETTINGS["documentary"] = dict(_DEVELOP_SETTINGS["neutral"])


def _scene_signals(scenario: str) -> SceneSignals:
    values = {
        "landscape": dict(
            primary_subject_type="landscape",
            primary_subject="mountain landscape",
            scene_category="scenic_travel",
            lighting_type="daylight",
            dynamic_range="high",
            color_character="balanced",
            confidence=0.92,
            editing_priorities=["Improve tonal separation", "Recover sky detail"],
        ),
        "architecture": dict(
            primary_subject_type="architecture",
            primary_subject="building",
            scene_category="architecture",
            architecture_dominant=True,
            lighting_type="daylight",
            dynamic_range="high",
            confidence=0.9,
        ),
        "portrait": dict(
            primary_subject_type="person",
            primary_subject="portrait",
            scene_category="portrait",
            people_present=True,
            portrait_dominant=True,
            lighting_type="daylight",
            confidence=0.92,
        ),
        "documentary": dict(
            primary_subject_type="people",
            primary_subject="candid people",
            scene_category="documentary",
            people_present=True,
            documentary_context=True,
            lighting_type="daylight",
            confidence=0.91,
        ),
        "night": dict(
            primary_subject_type="nightscape",
            primary_subject="night scene",
            scene_category="night",
            night_scene=True,
            lighting_type="low_light",
            dynamic_range="high",
            confidence=0.9,
        ),
    }.get(
        scenario,
        {
            "primary_subject_type": "unknown",
            "scene_category": "unknown",
            "confidence": 0.0,
        },
    )
    return SceneSignals.model_validate(values)


class FakeModelClient(ModelClient):
    """Return deterministic model-like recommendations without external access."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        scenario: str = "auto",
    ) -> None:
        if scenario not in _SUPPORTED_SCENARIOS:
            supported = ", ".join(sorted(_SUPPORTED_SCENARIOS))
            raise ValueError(
                f"Unknown fake model scenario {scenario!r}; expected one of: "
                f"{supported}."
            )
        self.model_name = model_name
        self.scenario = scenario
        self.invocations: list[dict[str, str]] = []

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """Return deterministic analysis for a validated request."""

        scenario = self._select_scenario(request)
        selection = select_style(
            request.options.style_profile,
            _scene_signals(scenario),
        )
        self._record(request)
        self._raise_for_invalid_output(scenario)
        return AnalyzeResponse(
            schema_version="1.0",
            request_id=request.request_id,
            filename=request.filename,
            status="success",
            requested_style_id=selection.requested_style_id,
            effective_style_id=selection.effective_style_id,
            style_selection_mode=selection.mode,
            style_selection_reason=selection.reason,
            editing_intensity=selection.editing_intensity,
            scene_confidence=selection.scene.confidence,
            analysis=self._build_analysis(scenario),
            edit_plan=self._build_edit_plan(
                scenario,
                selection.effective_style_id,
            ),
            crop=self._build_crop(scenario, request.options.include_crop),
            leveling=self._build_leveling(scenario),
            denoise=self._build_denoise(
                scenario,
                request.options.include_denoise,
                request.exif.iso,
            ),
            warnings=[],
            model=request.model or "gemma",
            resolved_model=self._resolved_model(request),
            processing_duration_ms=1,
        )

    async def develop(
        self,
        request: DevelopRequest,
        profile: StyleProfile | None = None,
    ) -> DevelopResponse:
        """Return deterministic raw develop recommendations."""

        scenario = self._select_scenario(request)
        selection = select_style(
            request.options.style_profile,
            _scene_signals(scenario),
        )
        self._record(request)
        self._raise_for_invalid_output(scenario)
        profile_id = (
            profile.id if profile is not None else selection.effective_style_id
        )
        return DevelopResponse(
            schema_version="1.0",
            request_id=request.request_id,
            filename=request.filename,
            status="success",
            requested_style_id=selection.requested_style_id,
            effective_style_id=profile_id,
            style_selection_mode=selection.mode,
            style_selection_reason=selection.reason,
            editing_intensity=selection.editing_intensity,
            scene_confidence=selection.scene.confidence,
            analysis=self._build_analysis(scenario),
            edit_plan=self._build_edit_plan(scenario, profile_id),
            develop_settings=DevelopSettings.model_validate(
                _DEVELOP_SETTINGS[scenario]
            ),
            crop=self._build_crop(scenario, request.options.include_crop),
            leveling=self._build_leveling(scenario),
            denoise=self._build_denoise(
                scenario,
                request.options.include_denoise,
                request.exif.iso,
            ),
            warnings=[],
            model=request.model or "gemma",
            resolved_model=self._resolved_model(request),
            processing_duration_ms=1,
        )

    def _select_scenario(
        self,
        request: AnalyzeRequest | DevelopRequest,
    ) -> str:
        if self.scenario != "auto":
            return self.scenario

        normalized_filename = request.filename.casefold()
        for scenario in _FILENAME_SCENARIOS:
            if scenario in normalized_filename:
                return scenario
        if request.exif.iso is not None and request.exif.iso >= 3200:
            return "high_iso"
        return "neutral"

    def _raise_for_invalid_output(self, scenario: str) -> None:
        if scenario == "invalid_output":
            raise ModelResponseError(
                "Fake model scenario requested invalid output.",
                model_name=self.model_name or "fake-autodevelop-v1",
                code="invalid_fake_output",
            )

    def _record(self, request: AnalyzeRequest | DevelopRequest) -> None:
        stable_model = request.model or "gemma"
        self.invocations.append(
            {
                "model": stable_model,
                "resolved_model": self._resolved_model(request),
                "style_profile": request.options.style_profile,
                "filename": request.filename,
            }
        )

    @property
    def invocation_count(self) -> int:
        return len(self.invocations)

    def _resolved_model(
        self,
        request: AnalyzeRequest | DevelopRequest,
    ) -> str:
        if self.model_name is not None:
            return self.model_name
        return {
            "gemma": "gemma-4-31b",
            "qwen": "qwen_qwen3-vl-32b-instruct",
            "gpt_oss": "gpt-oss",
            "gemini": "gemini-2.5-flash",
        }.get(request.model or "gemma", "fake-autodevelop-v1")

    @staticmethod
    def _build_analysis(scenario: str) -> TechnicalAnalysis:
        return TechnicalAnalysis.model_validate(_ANALYSIS_DATA[scenario])

    @staticmethod
    def _build_edit_plan(scenario: str, profile_id: str) -> EditPlan:
        goals, cautions = _PLAN_DATA[scenario]
        return EditPlan(
            style_profile=profile_id,
            goals=list(goals),
            cautions=list(cautions),
        )

    @staticmethod
    def _build_crop(
        scenario: str,
        include_crop: bool,
    ) -> CropRecommendation | None:
        if not include_crop:
            return None
        if scenario == "landscape":
            return CropRecommendation(
                recommended=True,
                left=0.02,
                right=0.98,
                top=0.03,
                bottom=0.97,
                confidence=0.88,
                reason="Remove narrow edge distractions.",
            )
        if scenario == "architecture":
            return CropRecommendation(
                recommended=True,
                left=0.02,
                right=0.98,
                top=0.02,
                bottom=0.98,
                confidence=0.90,
                reason="Improve architectural frame balance.",
            )
        return CropRecommendation(
            recommended=False,
            confidence=0.95,
            reason="No crop change is needed for this fake scenario.",
        )

    @staticmethod
    def _build_leveling(scenario: str) -> LevelingRecommendation:
        if scenario == "architecture":
            return LevelingRecommendation(
                recommended=True,
                angle=0.4,
                mode="vertical",
            )
        return LevelingRecommendation(
            recommended=False,
            angle=0,
            mode="none",
        )

    @staticmethod
    def _build_denoise(
        scenario: str,
        include_denoise: bool,
        iso: int | None,
    ) -> DenoiseRecommendation | None:
        if not include_denoise:
            return None
        if scenario == "high_iso":
            return DenoiseRecommendation(
                recommended=True,
                amount=45.0,
                confidence=0.95,
                reason="High ISO metadata indicates substantial noise.",
            )
        if scenario == "night":
            return DenoiseRecommendation(
                recommended=True,
                amount=35.0,
                confidence=0.90,
                reason="Night processing benefits from moderate denoise.",
            )
        if scenario == "portrait" and iso is not None and iso >= 1600:
            return DenoiseRecommendation(
                recommended=True,
                amount=20.0,
                confidence=0.88,
                reason="Portrait ISO indicates visible noise may need reduction.",
            )
        return DenoiseRecommendation(
            recommended=False,
            amount=None,
            confidence=0.90,
            reason="Denoise is not needed for this fake scenario.",
        )
