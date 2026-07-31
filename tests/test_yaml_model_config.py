import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from autodevelop.config import Settings, get_settings
from autodevelop.config_loader import (
    ModelConfigurationError,
    load_models_yaml,
    load_settings,
    parse_models_yaml,
)
from autodevelop.main import create_app
from autodevelop.model_clients import FakeModelClient, ModelResolver
from autodevelop.models import AnalyzeRequest, DevelopRequest

MODEL_ENVIRONMENT_VARIABLES = (
    "AUTODEVELOP_CONFIG_FILE",
    "AUTODEVELOP_DEFAULT_MODEL",
    "AUTODEVELOP_LOCAL_BASE_URL",
    "AUTODEVELOP_LOCAL_API_KEY",
    "AUTODEVELOP_LOCAL_TIMEOUT_SECONDS",
    "AUTODEVELOP_GEMMA_MODEL",
    "AUTODEVELOP_QWEN_MODEL",
    "AUTODEVELOP_GPT_OSS_MODEL",
    "AUTODEVELOP_GEMINI_API_KEY",
    "AUTODEVELOP_GEMINI_MODEL",
    "AUTODEVELOP_GEMINI_TIMEOUT_SECONDS",
    "AUTODEVELOP_LEARNING_ENABLED",
    "AUTODEVELOP_LEARNING_DB",
    "AUTODEVELOP_LEARNING_MIN_SAMPLES",
    "AUTODEVELOP_LEARNING_MAX_RESULTS",
    "AUTODEVELOP_LEARNING_MIN_SIMILARITY",
    "AUTODEVELOP_LEARNING_MAX_CANDIDATE_POOL",
)
IDENTITY_FIELDS = (
    "schema_version",
    "request_id",
    "filename",
    "model",
    "resolved_model",
)
REQUEST_ID = "ffffffff-ffff-4fff-8fff-ffffffffffff"


@pytest.fixture(autouse=True)
def clean_model_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in MODEL_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def _write_config(root: Path, content: str, name: str = "config/models.yaml") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _load(root: Path) -> Settings:
    return load_settings(application_root=root, env_file=None)


def test_missing_default_yaml_uses_built_in_defaults(tmp_path: Path) -> None:
    settings = _load(tmp_path)

    assert settings.default_model == "gemma"
    assert settings.gemma_model == "gemma-4-31b"
    assert settings.yaml_configuration_loaded is False
    assert settings.configuration_source_summary == "built-in"


def test_valid_yaml_loads_all_non_secret_fields(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
version: 1
default_model: qwen
providers:
  local:
    base_url: http://local.example:1234/v1/
    timeout_seconds: 111
  gemini:
    timeout_seconds: 222
models:
  gemma:
    provider_model_id: yaml-gemma
  qwen:
    provider_model_id: yaml-qwen
  gpt_oss:
    provider_model_id: yaml-gpt
  gemini:
    provider_model_id: yaml-gemini
  claude:
    enabled: false
learning:
  enabled: false
  database_path: data/custom-learning.sqlite3
  minimum_samples: 4
  maximum_results: 6
  minimum_similarity: 0.75
  maximum_candidate_pool: 120
""",
    )

    settings = _load(tmp_path)

    assert settings.default_model == "qwen"
    assert settings.local_base_url == "http://local.example:1234/v1"
    assert settings.local_timeout_seconds == 111
    assert settings.gemini_timeout_seconds == 222
    assert settings.gemma_model == "yaml-gemma"
    assert settings.qwen_model == "yaml-qwen"
    assert settings.gpt_oss_model == "yaml-gpt"
    assert settings.gemini_model == "yaml-gemini"
    assert settings.learning_enabled is False
    assert settings.learning_db == (
        tmp_path / "data" / "custom-learning.sqlite3"
    ).resolve()
    assert settings.learning_min_samples == 4
    assert settings.learning_max_results == 6
    assert settings.learning_min_similarity == 0.75
    assert settings.learning_max_candidate_pool == 120
    assert settings.yaml_configuration_loaded is True
    assert settings.configuration_source_summary == "yaml"


@pytest.mark.parametrize("content", ["", "# intentionally empty\n"])
def test_empty_yaml_is_an_empty_configuration(
    tmp_path: Path,
    content: str,
) -> None:
    _write_config(tmp_path, content)

    settings = _load(tmp_path)

    assert settings.default_model == "gemma"
    assert settings.yaml_configuration_loaded is True


@pytest.mark.parametrize(
    "content",
    [
        "models: [",
        "- not\n- a\n- mapping\n",
        "version: 2\n",
        "unknown: true\n",
        "defaut_model: qwen\n",
        "providers:\n  misspelled:\n    timeout_seconds: 120\n",
        "models:\n  unknown:\n    provider_model_id: value\n",
        "default_model: gemma\ndefault_model: qwen\n",
    ],
    ids=[
        "malformed",
        "non-mapping",
        "unsupported-version",
        "unknown-top-level",
        "misspelled-top-level",
        "unknown-provider",
        "unknown-model",
        "duplicate-key",
    ],
)
def test_invalid_yaml_fails_clearly(tmp_path: Path, content: str) -> None:
    _write_config(tmp_path, content)

    with pytest.raises(ModelConfigurationError):
        _load(tmp_path)


def test_missing_explicit_config_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ModelConfigurationError, match="not found"):
        load_settings(
            config_file=tmp_path / "missing.yaml",
            application_root=tmp_path,
            env_file=None,
        )


def test_missing_environment_config_file_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AUTODEVELOP_CONFIG_FILE",
        str(tmp_path / "missing-from-environment.yaml"),
    )

    with pytest.raises(ModelConfigurationError, match="not found"):
        _load(tmp_path)


def test_malformed_yaml_error_retains_no_raw_cause() -> None:
    marker = "sensitive-yaml-marker"

    with pytest.raises(ModelConfigurationError) as raised:
        parse_models_yaml(f"{marker}: [")

    assert marker not in str(raised.value)
    assert raised.value.__cause__ is None


def test_relative_explicit_path_uses_application_root(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "default_model: qwen\n",
        name="custom/models.yaml",
    )

    settings = load_settings(
        config_file="custom/models.yaml",
        application_root=tmp_path,
        env_file=None,
    )

    assert settings.default_model == "qwen"


def test_tilde_in_explicit_path_is_expanded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _write_config(tmp_path, "default_model: qwen\n", name="models.yaml")

    settings = load_settings(
        config_file="~/models.yaml",
        application_root=tmp_path / "different-root",
        env_file=None,
    )

    assert settings.default_model == "qwen"


def test_default_path_does_not_depend_on_current_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(
        tmp_path,
        (
            "default_model: qwen\n"
            "learning:\n"
            "  database_path: data/from-stable-root.sqlite3\n"
        ),
    )
    other_directory = tmp_path / "elsewhere"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)

    settings = _load(tmp_path)
    settings.log_path = tmp_path / "logs" / "different-cwd.log"
    app = create_app(settings, model_client=FakeModelClient())

    assert settings.default_model == "qwen"
    assert settings.learning_db == (
        tmp_path / "data" / "from-stable-root.sqlite3"
    ).resolve()
    with TestClient(app) as client:
        assert client.get("/autodevelop/v1/health").status_code == 200
    assert settings.learning_db.is_file()
    assert settings.learning_db.parent.is_dir()


def test_absolute_learning_database_path_is_preserved(tmp_path: Path) -> None:
    absolute_path = (tmp_path / "external" / "learning.sqlite3").resolve()
    _write_config(
        tmp_path,
        f"learning:\n  database_path: {absolute_path.as_posix()}\n",
    )

    assert _load(tmp_path).learning_db == absolute_path


@pytest.mark.parametrize(
    "learning_yaml",
    [
        "enabled: 'true'",
        "database_path: '   '",
        "minimum_samples: 0",
        "minimum_samples: '3'",
        "maximum_results: 0",
        "maximum_results: '5'",
        "minimum_similarity: -0.01",
        "minimum_similarity: 1.01",
        "minimum_similarity: '0.70'",
        "maximum_candidate_pool: 0",
        "maximum_candidate_pool: '100'",
        "maximum_results: 6\nmaximum_candidate_pool: 5",
    ],
)
def test_invalid_learning_yaml_fails_clearly(
    tmp_path: Path,
    learning_yaml: str,
) -> None:
    _write_config(
        tmp_path,
        "learning:\n  " + learning_yaml.replace("\n", "\n  ") + "\n",
    )

    with pytest.raises(
        ModelConfigurationError,
        match=r"learning(?:\.|$)",
    ):
        _load(tmp_path)


def test_unknown_learning_key_is_rejected(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "learning:\n  enabled: true\n  database: private.sqlite3\n",
    )

    with pytest.raises(ModelConfigurationError, match=r"learning\.<unknown-key>"):
        _load(tmp_path)


def test_learning_environment_variables_are_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(
        tmp_path,
        """
learning:
  enabled: true
  database_path: data/yaml-learning.sqlite3
  minimum_samples: 3
  maximum_results: 5
  minimum_similarity: 0.70
  maximum_candidate_pool: 100
""",
    )
    monkeypatch.setenv("AUTODEVELOP_LEARNING_ENABLED", "false")
    monkeypatch.setenv("AUTODEVELOP_LEARNING_DB", "private/env.sqlite3")
    monkeypatch.setenv("AUTODEVELOP_LEARNING_MIN_SAMPLES", "91")
    monkeypatch.setenv("AUTODEVELOP_LEARNING_MAX_RESULTS", "19")
    monkeypatch.setenv("AUTODEVELOP_LEARNING_MIN_SIMILARITY", "0.01")
    monkeypatch.setenv("AUTODEVELOP_LEARNING_MAX_CANDIDATE_POOL", "999")

    settings = _load(tmp_path)

    assert settings.learning_enabled is True
    assert settings.learning_db == (
        tmp_path / "data" / "yaml-learning.sqlite3"
    ).resolve()
    assert settings.learning_min_samples == 3
    assert settings.learning_max_results == 5
    assert settings.learning_min_similarity == 0.70
    assert settings.learning_max_candidate_pool == 100
    assert settings.configuration_sources["learning_enabled"] == "yaml"


def test_learning_dotenv_values_are_ignored_but_secrets_still_load(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
learning:
  enabled: true
  database_path: data/yaml-dotenv.sqlite3
  minimum_samples: 3
  maximum_results: 5
  minimum_similarity: 0.70
  maximum_candidate_pool: 100
""",
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "AUTODEVELOP_LEARNING_ENABLED=false",
                "AUTODEVELOP_LEARNING_DB=private/dotenv.sqlite3",
                "AUTODEVELOP_LEARNING_MIN_SAMPLES=90",
                "AUTODEVELOP_LEARNING_MAX_RESULTS=19",
                "AUTODEVELOP_LEARNING_MIN_SIMILARITY=0.01",
                "AUTODEVELOP_LEARNING_MAX_CANDIDATE_POOL=999",
                "AUTODEVELOP_LOCAL_API_KEY=dotenv-local-secret",
                "AUTODEVELOP_GEMINI_API_KEY=dotenv-gemini-secret",
            )
        ),
        encoding="utf-8",
    )

    settings = load_settings(
        application_root=tmp_path,
        env_file=env_path,
    )

    assert settings.learning_enabled is True
    assert settings.learning_db == (
        tmp_path / "data" / "yaml-dotenv.sqlite3"
    ).resolve()
    assert settings.learning_min_samples == 3
    assert settings.learning_max_results == 5
    assert settings.learning_min_similarity == 0.70
    assert settings.learning_max_candidate_pool == 100
    assert (
        settings.local_api_key.get_secret_value()
        == "dotenv-local-secret"
    )
    assert (
        settings.gemini_api_key.get_secret_value()
        == "dotenv-gemini-secret"
    )


@pytest.mark.parametrize(
    ("model_id", "attribute"),
    [
        ("gemma", "gemma_model"),
        ("qwen", "qwen_model"),
        ("gpt_oss", "gpt_oss_model"),
        ("gemini", "gemini_model"),
    ],
)
def test_each_provider_model_id_loads(
    tmp_path: Path,
    model_id: str,
    attribute: str,
) -> None:
    _write_config(
        tmp_path,
        f"models:\n  {model_id}:\n    provider_model_id: configured-value\n",
    )

    assert getattr(_load(tmp_path), attribute) == "configured-value"


@pytest.mark.parametrize(
    "content",
    [
        "default_model: claude\n",
        "models:\n  claude:\n    enabled: true\n",
        "models:\n  claude:\n    provider_model_id: forbidden\n",
        "models:\n  gemma:\n    enabled: false\n",
        "models:\n  gemma:\n    enabled: 'false'\n",
    ],
)
def test_unsupported_model_availability_configuration_fails(
    tmp_path: Path,
    content: str,
) -> None:
    _write_config(tmp_path, content)

    with pytest.raises(ModelConfigurationError):
        _load(tmp_path)


@pytest.mark.parametrize("model_value", ["''", "'   '"])
def test_blank_provider_model_id_fails(
    tmp_path: Path,
    model_value: str,
) -> None:
    _write_config(
        tmp_path,
        f"models:\n  gemma:\n    provider_model_id: {model_value}\n",
    )

    with pytest.raises(ModelConfigurationError):
        _load(tmp_path)


def test_provider_values_load_from_yaml(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
providers:
  local:
    base_url: http://192.0.2.1:1234/v1
    timeout_seconds: 10
  gemini:
    timeout_seconds: 600
""",
    )

    settings = _load(tmp_path)

    assert settings.local_base_url == "http://192.0.2.1:1234/v1"
    assert settings.local_timeout_seconds == 10
    assert settings.gemini_timeout_seconds == 600


@pytest.mark.parametrize(
    "content",
    [
        "providers:\n  local:\n    base_url: file:///tmp/provider\n",
        "providers:\n  local:\n    timeout_seconds: 9\n",
        "providers:\n  local:\n    timeout_seconds: 601\n",
        "providers:\n  local:\n    timeout_seconds: '120'\n",
        "providers:\n  gemini:\n    timeout_seconds: 9\n",
        "providers:\n  gemini:\n    timeout_seconds: 601\n",
    ],
)
def test_invalid_provider_configuration_fails(
    tmp_path: Path,
    content: str,
) -> None:
    _write_config(tmp_path, content)

    with pytest.raises(ModelConfigurationError):
        _load(tmp_path)


@pytest.mark.parametrize(
    ("environment_name", "environment_value", "yaml_content", "attribute", "expected"),
    [
        (
            "AUTODEVELOP_DEFAULT_MODEL",
            "qwen",
            "default_model: gemma\n",
            "default_model",
            "qwen",
        ),
        (
            "AUTODEVELOP_LOCAL_BASE_URL",
            "http://env.example:1234/v1",
            "providers:\n  local:\n    base_url: http://yaml.example:1234/v1\n",
            "local_base_url",
            "http://env.example:1234/v1",
        ),
        (
            "AUTODEVELOP_LOCAL_TIMEOUT_SECONDS",
            "321",
            "providers:\n  local:\n    timeout_seconds: 123\n",
            "local_timeout_seconds",
            321,
        ),
        (
            "AUTODEVELOP_GEMMA_MODEL",
            "env-gemma",
            "models:\n  gemma:\n    provider_model_id: yaml-gemma\n",
            "gemma_model",
            "env-gemma",
        ),
        (
            "AUTODEVELOP_QWEN_MODEL",
            "env-qwen",
            "models:\n  qwen:\n    provider_model_id: yaml-qwen\n",
            "qwen_model",
            "env-qwen",
        ),
        (
            "AUTODEVELOP_GPT_OSS_MODEL",
            "env-gpt",
            "models:\n  gpt_oss:\n    provider_model_id: yaml-gpt\n",
            "gpt_oss_model",
            "env-gpt",
        ),
        (
            "AUTODEVELOP_GEMINI_MODEL",
            "env-gemini",
            "models:\n  gemini:\n    provider_model_id: yaml-gemini\n",
            "gemini_model",
            "env-gemini",
        ),
        (
            "AUTODEVELOP_GEMINI_TIMEOUT_SECONDS",
            "432",
            "providers:\n  gemini:\n    timeout_seconds: 234\n",
            "gemini_timeout_seconds",
            432,
        ),
    ],
)
def test_environment_overrides_yaml_field_by_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
    environment_value: str,
    yaml_content: str,
    attribute: str,
    expected: str | int,
) -> None:
    _write_config(tmp_path, yaml_content)
    monkeypatch.setenv(environment_name, environment_value)

    settings = _load(tmp_path)

    assert getattr(settings, attribute) == expected
    assert settings.configuration_sources[attribute] == "environment"


def test_one_environment_override_preserves_unrelated_yaml_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(
        tmp_path,
        """
models:
  gemma:
    provider_model_id: yaml-gemma
  qwen:
    provider_model_id: yaml-qwen
""",
    )
    monkeypatch.setenv("AUTODEVELOP_QWEN_MODEL", "env-qwen")

    settings = _load(tmp_path)

    assert settings.gemma_model == "yaml-gemma"
    assert settings.qwen_model == "env-qwen"
    assert settings.configuration_sources["gemma_model"] == "yaml"
    assert settings.configuration_sources["qwen_model"] == "environment"
    assert settings.configuration_source_summary == "yaml+environment"


@pytest.mark.parametrize(
    "environment_name",
    [
        "AUTODEVELOP_DEFAULT_MODEL",
        "AUTODEVELOP_LOCAL_BASE_URL",
        "AUTODEVELOP_LOCAL_TIMEOUT_SECONDS",
        "AUTODEVELOP_GEMMA_MODEL",
        "AUTODEVELOP_QWEN_MODEL",
        "AUTODEVELOP_GPT_OSS_MODEL",
        "AUTODEVELOP_GEMINI_MODEL",
        "AUTODEVELOP_GEMINI_TIMEOUT_SECONDS",
    ],
)
def test_blank_environment_override_never_uses_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
) -> None:
    _write_config(
        tmp_path,
        """
default_model: qwen
providers:
  local:
    base_url: http://yaml.example:1234/v1
    timeout_seconds: 120
  gemini:
    timeout_seconds: 120
models:
  gemma:
    provider_model_id: yaml-gemma
  qwen:
    provider_model_id: yaml-qwen
  gpt_oss:
    provider_model_id: yaml-gpt
  gemini:
    provider_model_id: yaml-gemini
""",
    )
    monkeypatch.setenv(environment_name, "")

    with pytest.raises(ValidationError):
        _load(tmp_path)


@pytest.mark.parametrize(
    "content",
    [
        "local_api_key: exposed\n",
        "gemini_api_key: exposed\n",
        "providers:\n  local:\n    api_key: exposed\n",
        "providers:\n  gemini:\n    authorization: exposed\n",
    ],
)
def test_secret_like_yaml_fields_are_rejected(
    tmp_path: Path,
    content: str,
) -> None:
    _write_config(tmp_path, content)

    with pytest.raises(ModelConfigurationError) as raised:
        _load(tmp_path)

    assert "exposed" not in str(raised.value)


def test_api_keys_remain_environment_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTODEVELOP_LOCAL_API_KEY", "local-secret")
    monkeypatch.setenv("AUTODEVELOP_GEMINI_API_KEY", "gemini-secret")

    settings = _load(tmp_path)

    assert settings.local_api_key.get_secret_value() == "local-secret"
    assert settings.gemini_api_key.get_secret_value() == "gemini-secret"


def test_explicit_config_file_environment_variable_is_honored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_config(tmp_path, "default_model: qwen\n", name="custom.yaml")
    monkeypatch.setenv("AUTODEVELOP_CONFIG_FILE", str(path))

    assert _load(tmp_path).default_model == "qwen"


def test_get_settings_is_startup_cached_until_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_config(tmp_path, "default_model: gemma\n", name="startup.yaml")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTODEVELOP_CONFIG_FILE", str(path))
    get_settings.cache_clear()
    try:
        first = get_settings()
        path.write_text("default_model: qwen\n", encoding="utf-8")
        second = get_settings()
    finally:
        get_settings.cache_clear()

    assert first is second
    assert second.default_model == "gemma"


def test_model_resolver_uses_yaml_and_environment_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_config(
        tmp_path,
        """
models:
  gemma:
    provider_model_id: yaml-gemma
  qwen:
    provider_model_id: yaml-qwen
""",
    )
    monkeypatch.setenv("AUTODEVELOP_QWEN_MODEL", "env-qwen")
    settings = _load(tmp_path)
    resolver = ModelResolver(settings)

    assert resolver.resolve("gemma").resolved_model == "yaml-gemma"
    assert resolver.resolve("qwen").resolved_model == "env-qwen"


class StaticProviderClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0

    async def infer(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if "Identify only the observable semantic signals" in kwargs.get(
            "prompt", ""
        ):
            return {
                "primary_subject_type": "other",
                "primary_subject": "configured test scene",
                "scene_category": "commercial_general",
                "lighting_type": "daylight",
                "dynamic_range": "moderate",
                "color_character": "balanced",
                "confidence": 0.9,
                "editing_priorities": [],
            }
        return dict(self.payload)


def _request_body(endpoint: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "filename": "Yaml_Config.NEF",
        "model": "qwen",
        "preview_base64": "aW1hZ2U=",
        "options": {"style_profile": "natural_travel"},
    }
    if endpoint == "develop":
        body["options"].update(
            {
                "include_crop": True,
                "include_denoise": True,
                "dry_run": False,
                "preserve_current_adjustments": True,
            }
        )
    return body


def _provider_payload(endpoint: str, resolved_model: str) -> dict[str, Any]:
    body = _request_body(endpoint)
    if endpoint == "analyze":
        request = AnalyzeRequest.model_validate(body)
        response = asyncio.run(
            FakeModelClient(model_name=resolved_model).analyze(request)
        )
    else:
        request = DevelopRequest.model_validate(body)
        response = asyncio.run(
            FakeModelClient(model_name=resolved_model).develop(request)
        )
    payload = response.model_dump(mode="json")
    for field in IDENTITY_FIELDS:
        payload.pop(field)
    # Learning diagnostics are constructed by the backend, not supplied by a
    # provider response.
    payload.pop("learning", None)
    payload.pop("hdr_decision", None)
    for field in (
        "requested_style_id",
        "effective_style_id",
        "style_selection_mode",
        "style_selection_reason",
        "editing_intensity",
        "scene_confidence",
    ):
        payload.pop(field, None)
    return payload


@pytest.mark.parametrize("endpoint", ["analyze", "develop"])
def test_routes_report_yaml_resolved_provider_model(
    tmp_path: Path,
    endpoint: str,
) -> None:
    _write_config(
        tmp_path,
        "models:\n  qwen:\n    provider_model_id: yaml-qwen\n",
    )
    settings = _load(tmp_path)
    provider = StaticProviderClient(_provider_payload(endpoint, "yaml-qwen"))
    resolver = ModelResolver(
        settings,
        provider_clients={"qwen": provider},
    )
    app = create_app(settings, model_resolver=resolver)

    with TestClient(app) as client:
        response = client.post(
            f"/autodevelop/v1/{endpoint}",
            json=_request_body(endpoint),
        )

    assert response.status_code == 200
    assert response.json()["model"] == "qwen"
    assert response.json()["resolved_model"] == "yaml-qwen"
    assert provider.calls == 2


def test_models_endpoint_reflects_yaml_without_calling_provider(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
default_model: qwen
models:
  qwen:
    provider_model_id: yaml-qwen
  gemini:
    provider_model_id: yaml-gemini
""",
    )
    settings = _load(tmp_path)
    provider = StaticProviderClient({})
    resolver = ModelResolver(
        settings,
        provider_clients={"qwen": provider},
    )
    app = create_app(settings, model_resolver=resolver)

    with TestClient(app) as client:
        response = client.get("/autodevelop/v1/models")

    qwen = next(item for item in response.json()["models"] if item["id"] == "qwen")
    gemini = next(
        item for item in response.json()["models"] if item["id"] == "gemini"
    )
    assert response.json()["default_model"] == "qwen"
    assert qwen["configured_model"] == "yaml-qwen"
    assert gemini["configured_model"] == "yaml-gemini"
    assert gemini["status"] == "not_configured"
    assert "configuration_sources" not in response.text
    assert "config_file" not in response.text
    assert provider.calls == 0


def test_startup_log_is_safe_and_does_not_dump_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    yaml_marker = "yaml-provider-marker"
    local_secret = "local-api-secret"
    gemini_secret = "gemini-api-secret"
    _write_config(
        tmp_path,
        (
            f"models:\n  gemma:\n    provider_model_id: {yaml_marker}\n"
            "learning:\n"
            "  enabled: true\n"
            "  database_path: data/log-test.sqlite3\n"
            "  minimum_samples: 3\n"
            "  maximum_results: 5\n"
            "  minimum_similarity: 0.70\n"
            "  maximum_candidate_pool: 100\n"
        ),
    )
    monkeypatch.setenv("AUTODEVELOP_LOCAL_API_KEY", local_secret)
    monkeypatch.setenv("AUTODEVELOP_GEMINI_API_KEY", gemini_secret)
    settings = _load(tmp_path)
    log_path = tmp_path / "startup.log"
    settings.log_path = log_path
    app = create_app(settings, model_client=FakeModelClient())

    with TestClient(app) as client:
        assert client.get("/autodevelop/v1/health").status_code == 200

    log_text = log_path.read_text(encoding="utf-8")
    assert "configuration_loaded" in log_text
    assert "config_source=yaml" in log_text
    assert "learning_enabled=true" in log_text
    assert "learning_database_configured=true" in log_text
    assert "learning_minimum_samples=3" in log_text
    assert "learning_maximum_results=5" in log_text
    assert "learning_minimum_similarity=0.70" in log_text
    assert str(settings.learning_db) not in log_text
    assert local_secret not in log_text
    assert gemini_secret not in log_text
    assert yaml_marker not in log_text
