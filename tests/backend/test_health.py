from autodevelop.api.routes.health import health
from autodevelop.config import Settings


def test_health_response() -> None:
    response = health()

    assert response.status == "ok"
    assert response.service == "AutoDevelop AI"
    assert response.version == "0.1.0"


def test_default_backend_configuration() -> None:
    settings = Settings(_env_file=None)

    assert settings.port == 8005
    assert settings.api_prefix == "/autodevelop/v1"
    assert settings.database_path.as_posix() == "data/autodevelop.db"
    assert settings.log_path.as_posix() == "logs/autodevelop.log"
    assert settings.temp_dir.as_posix() == "temp"
