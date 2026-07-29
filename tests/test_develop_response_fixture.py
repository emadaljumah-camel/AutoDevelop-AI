"""Keep the Lightroom wire fixture aligned with the live Develop endpoint."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from autodevelop.config import Settings
from autodevelop.main import create_app
from autodevelop.model_clients import FakeModelClient


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "develop_response.json"
)


def test_representative_fixture_matches_current_develop_response(
    tmp_path: Path,
) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    app = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "autodevelop.log",
        ),
        model_client=FakeModelClient(),
    )
    request = {
        "schema_version": "1.0",
        "request_id": fixture["request_id"],
        "filename": fixture["filename"],
        "model": "gpt_oss",
        "preview_path": "not-read.jpg",
        "exif": {"iso": 800},
        "options": {
            "style_profile": "natural_travel",
            "include_crop": True,
            "include_denoise": True,
        },
    }

    with TestClient(app) as client:
        response = client.post("/autodevelop/v1/develop", json=request)

    assert response.status_code == 200
    assert response.json() == fixture
