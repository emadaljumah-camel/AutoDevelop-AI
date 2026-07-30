# AutoDevelop AI

AutoDevelop AI is a separate Lightroom Classic automation project composed of:

- the `AutoDevelopAI.lrplugin` Lightroom Classic Lua plug-in;
- a Python 3.12 FastAPI backend;
- an LM Studio-compatible model client;
- file-based JSON style profiles;
- SQLite edit-session storage; and
- backend and integration tests.

The plug-in supports Analyze, validated Auto Develop, style and model
selection, production preferences, and optional local personalized learning.

## Premium editing and automatic style selection

New Lightroom preferences default to **Auto** style selection. Auto uses a
strict scene-analysis pass and deterministic backend rules to select one of the
seven concrete style profiles. A saved or per-run manual style remains an exact
override.

Auto Develop assembles one provider-independent layered prompt from the master
editing philosophy, scene signals, effective style, qualitative editing
intensity, same-style learning preferences, Lightroom guidance, self-review,
and the strict output contract. Auto Develop uses scene preflight followed by
styled inference; manual Develop uses one inference call. Learning retrieval is
always scoped to the effective concrete style, and every recommendation still
passes through the existing SafetyValidator before Lightroom can apply it.

Composition cropping and rotational leveling are independent recommendations.
Each photo can receive crop only, level only, both, or neither. Crop decisions
address framing and visual hierarchy; leveling addresses accidental camera
roll using reliable horizons or structural lines. Perspective/Upright
correction is not implied. Lightroom combines accepted geometry into its crop
fields only at application time.

The plug-in exposes separate **Apply composition crop** and **Apply leveling
correction** preferences. Existing installations migrate the former
**Apply Crop** value to both controls, preserving an existing disabled choice.
Analyze remains read-only while reporting both geometry decisions separately.

## Requirements

- Python 3.12
- Lightroom Classic for loading the plug-in
- LM Studio for future local model integration
- ExifTool for future image metadata extraction

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

## Configure AI models

Copy the committed example to create a machine-local active configuration:

```powershell
Copy-Item config\models.example.yaml config\models.yaml
```

Edit provider model identifiers to match the models exposed by the configured
inference provider:

```yaml
models:
  gemma:
    provider_model_id: gemma-4-31b-qat

  qwen:
    provider_model_id: qwen3-vl-32b-instruct
```

Model, provider, and learning behavior is configured through YAML.
Environment variables remain supported for secrets and existing
application/runtime settings such as port and log paths.

Legacy `AUTODEVELOP_LEARNING_*` environment variables are ignored. Configure
learning behavior in the `learning` section of `config/models.yaml`.

To use a different YAML file:

```powershell
$env:AUTODEVELOP_CONFIG_FILE = "D:\AutoDevelop\my-models.yaml"
```

Relative custom paths are resolved from the AutoDevelop AI application root,
not the current console directory. The active `config/models.yaml` is ignored
by Git; commit only `config/models.example.yaml`.

YAML configuration is loaded once during backend startup. Configuration
changes require a backend restart. Automatic reload and file watching are not
enabled.

API keys and other credentials must not be placed in YAML. Configure
`AUTODEVELOP_LOCAL_API_KEY` and `AUTODEVELOP_GEMINI_API_KEY` through the
environment or local `.env` file only.

## Run the backend

```powershell
uvicorn autodevelop.main:app --app-dir backend --host 127.0.0.1 --port 8005
```

The health endpoint is available at:

```text
GET http://127.0.0.1:8005/autodevelop/v1/health
```

LM Studio defaults to its OpenAI-compatible API at
`http://127.0.0.1:1234/v1`. Local model output is parsed against the strict
Version 1 response contract and then passed through the SafetyValidator.

ExifTool defaults to the `exiftool` executable on `PATH`. Override
`AUTODEVELOP_EXIFTOOL_PATH` when it is installed elsewhere.

## Run tests

```powershell
python -m pytest
```

## Personalized learning

Phase 4 adds an optional local retrieval-based learning system. After a
successful Auto Develop, the plug-in can save the applied baseline. Adjust the
photo manually, select it, and run **AutoDevelop AI → Capture Editing
Feedback**. After at least three similar same-style examples, future Develop
requests may receive a compact aggregate preference block.

Learning does not fine-tune models, monitor Lightroom in the background, or
upload data. Its SQLite database defaults to
`data/autodevelop_learning.sqlite3`. See
[docs/LEARNING_SYSTEM.md](docs/LEARNING_SYSTEM.md) for storage, privacy,
configuration, reset, and backup details.

## Project layout

```text
AutoDevelopAI.lrplugin/  Lightroom Classic plug-in
backend/autodevelop/     FastAPI application package
profiles/                File-based JSON style profiles
data/                    SQLite database location
logs/                    Backend log location
temp/                    Temporary Lightroom previews
tests/backend/           Backend tests
tests/integration/       API integration tests
```

## Default paths

- API prefix: `/autodevelop/v1`
- Backend port: `8005`
- Database: `data/autodevelop.db`
- Learning database: `data/autodevelop_learning.sqlite3`
- Log: `logs/autodevelop.log`
- Temporary previews: `temp/`
