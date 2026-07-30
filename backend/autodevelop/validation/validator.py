"""Pure safety validation for model-generated editing recommendations."""

import math
from dataclasses import dataclass, field

from pydantic import JsonValue

from autodevelop.models import (
    CropRecommendation,
    DenoiseRecommendation,
    DevelopSettings,
    HdrRecommendation,
    LevelingRecommendation,
    ProcessingOptions,
    TechnicalAnalysis,
)
from autodevelop.profiles import StyleProfile
from autodevelop.validation import policies
from autodevelop.validation.models import (
    ValidationAction,
    ValidationIssue,
    ValidationResult,
)


def _is_finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _json_safe_value(value: object) -> JsonValue:
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


@dataclass
class _ValidationState:
    issues: list[ValidationIssue] = field(default_factory=list)
    rejected_fields: list[str] = field(default_factory=list)
    clamped_fields: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)

    def add_issue(
        self,
        *,
        code: str,
        message: str,
        field_name: str,
        original_value: object = None,
        adjusted_value: object = None,
        action: ValidationAction,
        severity: str = "warning",
        track_field: str | None = None,
    ) -> None:
        self.issues.append(
            ValidationIssue(
                code=code,
                message=message,
                field=field_name,
                original_value=_json_safe_value(original_value),
                adjusted_value=_json_safe_value(adjusted_value),
                action=action,
                severity=severity,
            )
        )
        tracked = track_field or field_name
        if action is ValidationAction.REJECTED:
            _append_unique(self.rejected_fields, tracked)
        elif action is ValidationAction.CLAMPED:
            _append_unique(self.clamped_fields, tracked)
        elif action is ValidationAction.REMOVED:
            _append_unique(self.removed_fields, tracked)


class SafetyValidator:
    """Normalize recommendations against one validated style profile."""

    def validate(
        self,
        *,
        settings: DevelopSettings | None,
        crop: CropRecommendation | None,
        denoise: DenoiseRecommendation | None,
        profile: StyleProfile,
        enable_hdr: HdrRecommendation | None = None,
        leveling: LevelingRecommendation | None = None,
        analysis: TechnicalAnalysis | None = None,
        options: ProcessingOptions | None = None,
    ) -> ValidationResult:
        """Return safe copies without mutating any source model."""

        state = _ValidationState()
        safe_settings = self._validate_settings(settings, profile, state)
        safe_crop = self._validate_crop(crop, profile, state)
        safe_leveling = self._validate_leveling(leveling, profile, state)
        safe_denoise = self._validate_denoise(denoise, profile, state)
        safe_hdr = self._validate_hdr(enable_hdr, analysis, options, state)
        is_safe = not any(issue.severity == "error" for issue in state.issues)
        return ValidationResult(
            is_safe=is_safe,
            settings=safe_settings,
            crop=safe_crop,
            leveling=safe_leveling,
            denoise=safe_denoise,
            enable_hdr=safe_hdr,
            issues=state.issues,
            rejected_fields=state.rejected_fields,
            clamped_fields=state.clamped_fields,
            removed_fields=state.removed_fields,
        )

    @staticmethod
    def _validate_hdr(
        recommendation: HdrRecommendation | None,
        analysis: TechnicalAnalysis | None,
        options: ProcessingOptions | None,
        state: _ValidationState,
    ) -> HdrRecommendation:
        safe_false = HdrRecommendation(recommended=False)
        if recommendation is None or not recommendation.recommended:
            return safe_false

        reasons: list[str] = []
        if options is None or not options.hdr_edit_supported:
            reasons.append("Lightroom HDR edit mode is not supported by the caller.")
        if options is not None and options.hdr_workflow == "sdr_only":
            reasons.append("The caller declared an SDR-only workflow.")
        if analysis is None:
            reasons.append("Structured scene evidence is unavailable.")
        else:
            dynamic_range = (analysis.dynamic_range or "").strip().lower()
            if dynamic_range != "high":
                reasons.append("The scene is not assessed as high dynamic range.")
            recoverability = {
                analysis.highlight_recoverability,
                analysis.shadow_recoverability,
            }
            if not recoverability.intersection({"moderate", "high"}):
                reasons.append("Useful RAW highlight or shadow recovery is unlikely.")
            if analysis.severe_underexposure:
                reasons.append("Severe underexposure makes HDR edit mode unsafe.")
            noise = (analysis.noise_level or "").strip().lower()
            if noise in {"high", "severe", "extreme"}:
                reasons.append("Noise is too high for a safe HDR recommendation.")

            scene = " ".join(
                value
                for value in (
                    analysis.scene_type,
                    analysis.main_subject,
                    analysis.lighting,
                    analysis.exposure_assessment,
                )
                if value
            ).lower()
            ordinary_people_scene = (
                any(word in scene for word in ("portrait", "headshot", "people"))
                and not any(
                    cue in scene
                    for cue in (
                        "sunset",
                        "sunrise",
                        "bright window",
                        "backlit",
                        "luminous",
                        "bright lights",
                    )
                )
            )
            if ordinary_people_scene:
                reasons.append("An ordinary people scene has no compelling HDR cue.")

        if reasons:
            state.add_issue(
                code=policies.HDR_RECOMMENDATION_REJECTED,
                message=" ".join(reasons),
                field_name="enable_hdr",
                original_value=True,
                adjusted_value=False,
                action=ValidationAction.REJECTED,
                track_field="enable_hdr",
            )
            return safe_false
        return HdrRecommendation(recommended=True)

    @staticmethod
    def _validate_settings(
        settings: DevelopSettings | None,
        profile: StyleProfile,
        state: _ValidationState,
    ) -> DevelopSettings:
        source = settings or DevelopSettings()
        safe_values: dict[str, float] = {}

        for field_name in DevelopSettings.model_fields:
            value = getattr(source, field_name, None)
            if value is None:
                continue
            if not _is_finite_number(value):
                state.add_issue(
                    code=policies.INVALID_NUMERIC_VALUE,
                    message=f"{field_name} is not a finite numeric value.",
                    field_name=field_name,
                    original_value=value,
                    action=ValidationAction.REJECTED,
                )
                continue

            slider_range = profile.slider_ranges.get(field_name)
            if slider_range is None:
                state.add_issue(
                    code=policies.SLIDER_NOT_ALLOWED,
                    message=f"{field_name} is not allowed by profile {profile.id}.",
                    field_name=field_name,
                    original_value=value,
                    action=ValidationAction.REMOVED,
                )
                continue

            adjusted_value = float(value)
            if value < slider_range.min:
                adjusted_value = slider_range.min
                state.add_issue(
                    code=policies.SLIDER_CLAMPED_LOW,
                    message=f"{field_name} was clamped to the profile minimum.",
                    field_name=field_name,
                    original_value=value,
                    adjusted_value=adjusted_value,
                    action=ValidationAction.CLAMPED,
                )
            elif value > slider_range.max:
                adjusted_value = slider_range.max
                state.add_issue(
                    code=policies.SLIDER_CLAMPED_HIGH,
                    message=f"{field_name} was clamped to the profile maximum.",
                    field_name=field_name,
                    original_value=value,
                    adjusted_value=adjusted_value,
                    action=ValidationAction.CLAMPED,
                )
            safe_values[field_name] = adjusted_value

        return DevelopSettings.model_validate(safe_values)

    def _validate_crop(
        self,
        crop: CropRecommendation | None,
        profile: StyleProfile,
        state: _ValidationState,
    ) -> CropRecommendation | None:
        if crop is None:
            return None
        if not isinstance(crop.recommended, bool):
            return self._reject_crop(
                state,
                policies.CROP_INVALID_BOUNDS,
                "Crop recommended flag must be boolean.",
                "crop.recommended",
                crop.recommended,
            )
        if not crop.recommended:
            return self._clean_nonrecommended_crop(crop, state)
        if not profile.crop_policy.allow_crop:
            return self._reject_crop(
                state,
                policies.CROP_NOT_ALLOWED,
                f"Crop is not allowed by profile {profile.id}.",
                "crop",
                True,
            )

        bounds = {
            "left": crop.left,
            "right": crop.right,
            "top": crop.top,
            "bottom": crop.bottom,
        }
        missing_bounds = [name for name, value in bounds.items() if value is None]
        if missing_bounds:
            return self._reject_crop(
                state,
                policies.CROP_MISSING_BOUNDS,
                f"Recommended crop is missing bounds: {', '.join(missing_bounds)}.",
                "crop",
                missing_bounds,
            )

        invalid_bounds = [
            name
            for name, value in bounds.items()
            if not _is_finite_number(value) or not 0 <= value <= 1
        ]
        if invalid_bounds:
            for name in invalid_bounds:
                state.add_issue(
                    code=policies.CROP_INVALID_BOUNDS,
                    message=f"crop.{name} must be finite and between 0 and 1.",
                    field_name=f"crop.{name}",
                    original_value=bounds[name],
                    action=ValidationAction.REJECTED,
                    track_field="crop",
                )
            return None

        left = float(bounds["left"])
        right = float(bounds["right"])
        top = float(bounds["top"])
        bottom = float(bounds["bottom"])
        if left >= right or top >= bottom:
            return self._reject_crop(
                state,
                policies.CROP_INVALID_BOUNDS,
                "Crop bounds must satisfy left < right and top < bottom.",
                "crop",
                [left, right, top, bottom],
            )

        edge_crops = (
            ("crop.left", left),
            ("crop.right", 1.0 - right),
            ("crop.top", top),
            ("crop.bottom", 1.0 - bottom),
        )
        max_edge_crop = profile.crop_policy.max_edge_crop
        edge_limit_exceeded = False
        for field_name, cropped_amount in edge_crops:
            if cropped_amount > max_edge_crop:
                edge_limit_exceeded = True
                edge_name = field_name.removeprefix("crop.")
                state.add_issue(
                    code=policies.CROP_EDGE_LIMIT_EXCEEDED,
                    message=(
                        f"Crop removes more from the {edge_name} edge "
                        "than the profile permits."
                    ),
                    field_name=field_name,
                    original_value=cropped_amount,
                    adjusted_value=max_edge_crop,
                    action=ValidationAction.REJECTED,
                    severity="warning",
                    track_field="crop",
                )
        if edge_limit_exceeded:
            return None

        retained_area = (right - left) * (bottom - top)
        if retained_area < profile.crop_policy.minimum_retained_area:
            return self._reject_crop(
                state,
                policies.CROP_AREA_TOO_SMALL,
                "Crop retains less image area than the profile permits.",
                "crop",
                retained_area,
            )

        confidence = crop.confidence
        if confidence is not None and not _is_finite_number(confidence):
            return self._reject_crop(
                state,
                policies.INVALID_NUMERIC_VALUE,
                "Crop confidence is not a finite numeric value.",
                "crop.confidence",
                confidence,
            )
        if confidence is None and profile.crop_policy.require_confidence:
            return self._reject_crop(
                state,
                policies.CROP_CONFIDENCE_REQUIRED,
                "Crop confidence is required by the selected profile.",
                "crop.confidence",
                None,
            )
        if (
            confidence is not None
            and confidence < profile.crop_policy.minimum_confidence
        ):
            return self._reject_crop(
                state,
                policies.CROP_CONFIDENCE_TOO_LOW,
                "Crop confidence is below the profile threshold.",
                "crop.confidence",
                confidence,
            )

        return CropRecommendation.model_validate(
            {
                "recommended": True,
                "left": left,
                "right": right,
                "top": top,
                "bottom": bottom,
                "confidence": confidence,
                "reason": crop.reason,
            }
        )

    @staticmethod
    def _clean_nonrecommended_crop(
        crop: CropRecommendation,
        state: _ValidationState,
    ) -> CropRecommendation:
        for field_name in ("left", "right", "top", "bottom"):
            value = getattr(crop, field_name, None)
            if value is not None:
                state.add_issue(
                    code=policies.CROP_VALUES_REMOVED_WHEN_NOT_RECOMMENDED,
                    message=f"crop.{field_name} was removed because crop is not recommended.",
                    field_name=f"crop.{field_name}",
                    original_value=value,
                    action=ValidationAction.REMOVED,
                )

        confidence = crop.confidence
        if confidence is not None and not _is_finite_number(confidence):
            state.add_issue(
                code=policies.INVALID_NUMERIC_VALUE,
                message="crop.confidence is not a finite numeric value.",
                field_name="crop.confidence",
                original_value=confidence,
                action=ValidationAction.REMOVED,
            )
            confidence = None
        return CropRecommendation.model_validate(
            {
                "recommended": False,
                "confidence": confidence,
                "reason": crop.reason,
            }
        )

    @staticmethod
    def _validate_leveling(
        leveling: LevelingRecommendation | None,
        profile: StyleProfile,
        state: _ValidationState,
    ) -> LevelingRecommendation:
        safe_false = LevelingRecommendation(
            recommended=False,
            angle=0,
            mode="none",
        )
        if leveling is None or not leveling.recommended:
            return safe_false
        if not profile.leveling_policy.allow_leveling:
            state.add_issue(
                code=policies.LEVELING_NOT_ALLOWED,
                message="Leveling is not allowed by the selected profile.",
                field_name="leveling",
                original_value=True,
                adjusted_value=False,
                action=ValidationAction.REJECTED,
            )
            return safe_false
        if not _is_finite_number(leveling.angle) or leveling.mode == "none":
            state.add_issue(
                code=policies.LEVELING_INVALID_STATE,
                message="Recommended leveling requires a finite angle and active mode.",
                field_name="leveling",
                original_value=leveling.model_dump(mode="json"),
                adjusted_value=False,
                action=ValidationAction.REJECTED,
            )
            return safe_false

        limit = profile.leveling_policy.maximum_absolute_angle
        adjusted = max(-limit, min(limit, float(leveling.angle)))
        if adjusted != leveling.angle:
            state.add_issue(
                code=policies.LEVELING_ANGLE_CLAMPED,
                message="Leveling angle was clamped to the profile limit.",
                field_name="leveling.angle",
                original_value=leveling.angle,
                adjusted_value=adjusted,
                action=ValidationAction.CLAMPED,
            )
        return LevelingRecommendation(
            recommended=True,
            angle=adjusted,
            mode=leveling.mode,
        )

    def _validate_denoise(
        self,
        denoise: DenoiseRecommendation | None,
        profile: StyleProfile,
        state: _ValidationState,
    ) -> DenoiseRecommendation | None:
        if denoise is None:
            return None
        if not isinstance(denoise.recommended, bool):
            state.add_issue(
                code=policies.INVALID_NUMERIC_VALUE,
                message="Denoise recommended flag must be boolean.",
                field_name="denoise.recommended",
                original_value=denoise.recommended,
                adjusted_value=False,
                action=ValidationAction.REJECTED,
                track_field="denoise",
            )
            return DenoiseRecommendation(
                recommended=False,
                reason=denoise.reason,
            )
        if not denoise.recommended:
            return self._clean_nonrecommended_denoise(denoise, state)
        if not profile.denoise_policy.allow_denoise:
            return self._reject_denoise(denoise, state, policies.DENOISE_NOT_ALLOWED)

        confidence = denoise.confidence
        if confidence is not None and not _is_finite_number(confidence):
            state.add_issue(
                code=policies.INVALID_NUMERIC_VALUE,
                message="denoise.confidence is not a finite numeric value.",
                field_name="denoise.confidence",
                original_value=confidence,
                action=ValidationAction.REMOVED,
            )
            confidence = None
        if (
            confidence is not None
            and confidence < profile.denoise_policy.minimum_confidence
        ):
            return self._reject_denoise(
                denoise,
                state,
                policies.DENOISE_CONFIDENCE_TOO_LOW,
            )

        amount = denoise.amount
        if amount is None:
            state.add_issue(
                code=policies.DENOISE_AMOUNT_MISSING,
                message="Recommended denoise has no amount; no value was invented.",
                field_name="denoise.amount",
                action=ValidationAction.ACCEPTED,
            )
        elif not _is_finite_number(amount):
            state.add_issue(
                code=policies.INVALID_NUMERIC_VALUE,
                message="denoise.amount is not a finite numeric value.",
                field_name="denoise.amount",
                original_value=amount,
                action=ValidationAction.REMOVED,
            )
            amount = None
        elif amount < profile.denoise_policy.minimum_amount:
            adjusted = profile.denoise_policy.minimum_amount
            state.add_issue(
                code=policies.DENOISE_AMOUNT_CLAMPED_LOW,
                message="Denoise amount was clamped to the profile minimum.",
                field_name="denoise.amount",
                original_value=amount,
                adjusted_value=adjusted,
                action=ValidationAction.CLAMPED,
            )
            amount = adjusted
        elif amount > profile.denoise_policy.maximum_amount:
            adjusted = profile.denoise_policy.maximum_amount
            state.add_issue(
                code=policies.DENOISE_AMOUNT_CLAMPED_HIGH,
                message="Denoise amount was clamped to the profile maximum.",
                field_name="denoise.amount",
                original_value=amount,
                adjusted_value=adjusted,
                action=ValidationAction.CLAMPED,
            )
            amount = adjusted

        return DenoiseRecommendation.model_validate(
            {
                "recommended": True,
                "amount": amount,
                "confidence": confidence,
                "reason": denoise.reason,
            }
        )

    @staticmethod
    def _clean_nonrecommended_denoise(
        denoise: DenoiseRecommendation,
        state: _ValidationState,
    ) -> DenoiseRecommendation:
        if denoise.amount is not None:
            state.add_issue(
                code=policies.DENOISE_AMOUNT_REMOVED_WHEN_NOT_RECOMMENDED,
                message="Denoise amount was removed because denoise is not recommended.",
                field_name="denoise.amount",
                original_value=denoise.amount,
                action=ValidationAction.REMOVED,
            )
        confidence = denoise.confidence
        if confidence is not None and not _is_finite_number(confidence):
            state.add_issue(
                code=policies.INVALID_NUMERIC_VALUE,
                message="denoise.confidence is not a finite numeric value.",
                field_name="denoise.confidence",
                original_value=confidence,
                action=ValidationAction.REMOVED,
            )
            confidence = None
        return DenoiseRecommendation.model_validate(
            {
                "recommended": False,
                "confidence": confidence,
                "reason": denoise.reason,
            }
        )

    @staticmethod
    def _reject_crop(
        state: _ValidationState,
        code: str,
        message: str,
        field_name: str,
        original_value: object,
    ) -> None:
        state.add_issue(
            code=code,
            message=message,
            field_name=field_name,
            original_value=original_value,
            action=ValidationAction.REJECTED,
            track_field="crop",
        )
        return None

    @staticmethod
    def _reject_denoise(
        denoise: DenoiseRecommendation,
        state: _ValidationState,
        code: str,
    ) -> DenoiseRecommendation:
        state.add_issue(
            code=code,
            message="Denoise recommendation was rejected by the selected profile.",
            field_name="denoise",
            original_value=denoise.confidence,
            adjusted_value=False,
            action=ValidationAction.REJECTED,
            track_field="denoise",
        )
        if denoise.amount is not None:
            state.add_issue(
                code=policies.DENOISE_AMOUNT_REMOVED_WHEN_NOT_RECOMMENDED,
                message="Denoise amount was removed from the rejected recommendation.",
                field_name="denoise.amount",
                original_value=denoise.amount,
                action=ValidationAction.REMOVED,
            )
        confidence = (
            denoise.confidence
            if _is_finite_number(denoise.confidence)
            else None
        )
        return DenoiseRecommendation.model_validate(
            {
                "recommended": False,
                "confidence": confidence,
                "reason": denoise.reason,
            }
        )
