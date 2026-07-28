from pathlib import Path

from fastapi.testclient import TestClient

from autodevelop.config import Settings
from autodevelop.main import create_app


def test_versioned_health_endpoint(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            log_path=tmp_path / "autodevelop.log",
        )
    )

    with TestClient(app) as client:
        response = client.get("/autodevelop/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AutoDevelop AI",
        "version": "0.1.0",
    }
    assert (tmp_path / "autodevelop.log").is_file()
