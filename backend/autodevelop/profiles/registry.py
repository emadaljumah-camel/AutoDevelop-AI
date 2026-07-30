"""Display metadata and ordering for bundled AutoDevelop AI styles."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class StyleDefinition:
    """Immutable display metadata for a bundled style profile."""

    id: str
    display_name: str
    description: str
    sort_order: int


AUTO_STYLE_ID: Final = "auto"
DEFAULT_STYLE_ID: Final = AUTO_STYLE_ID

_STYLES: Final[tuple[StyleDefinition, ...]] = (
    StyleDefinition(
        id="natural_travel",
        display_name="Natural Travel",
        description=(
            "Balanced, natural edits for travel and general photography."
        ),
        sort_order=1,
    ),
    StyleDefinition(
        id="landscape_impact",
        display_name="Landscape Impact",
        description=(
            "Stronger depth, contrast, atmosphere, and color separation "
            "for landscapes."
        ),
        sort_order=2,
    ),
    StyleDefinition(
        id="architecture",
        display_name="Architecture",
        description=(
            "Clean tonal control, structure, highlight protection, and "
            "restrained color."
        ),
        sort_order=3,
    ),
    StyleDefinition(
        id="stock_neutral",
        display_name="Stock Neutral",
        description=(
            "Neutral, commercially usable edits with controlled contrast "
            "and saturation."
        ),
        sort_order=4,
    ),
    StyleDefinition(
        id="portrait",
        display_name="Portrait",
        description=(
            "Gentle skin-friendly contrast, protected highlights, and "
            "restrained texture."
        ),
        sort_order=5,
    ),
    StyleDefinition(
        id="night",
        display_name="Night",
        description=(
            "Controlled shadows, protected highlights, noise-aware "
            "contrast, and balanced color."
        ),
        sort_order=6,
    ),
    StyleDefinition(
        id="documentary",
        display_name="Documentary",
        description=(
            "Realistic, restrained edits that preserve atmosphere, "
            "context, and authentic color."
        ),
        sort_order=7,
    ),
)

_STYLES_BY_ID: Final = {style.id: style for style in _STYLES}


def list_styles() -> tuple[StyleDefinition, ...]:
    """Return the immutable styles in their display order."""

    return _STYLES


def get_style(profile_id: str) -> StyleDefinition | None:
    """Return immutable metadata for a profile ID, if registered."""

    return _STYLES_BY_ID.get(profile_id)


def is_valid_style_id(profile_id: str) -> bool:
    """Return whether a profile ID is registered."""

    return profile_id in _STYLES_BY_ID


def is_valid_style_request_id(profile_id: str) -> bool:
    """Return whether a request selects Auto or a registered manual profile."""

    return profile_id == AUTO_STYLE_ID or is_valid_style_id(profile_id)
