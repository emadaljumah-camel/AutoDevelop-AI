# AutoDevelop AI

AutoDevelop AI is a separate Lightroom Classic automation project composed of:

- the `AutoDevelopAI.lrplugin` Lightroom Classic Lua plug-in;
- a Python 3.12 FastAPI backend;
- an LM Studio-compatible model client;
- file-based JSON style profiles;
- SQLite edit-session storage; and
- backend and integration tests.

This initial version is a repository skeleton. It does not include a
vision-model prompt or Lightroom editing behavior.

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

Configuration precedence is:

1. environment variable;
2. `config/models.yaml`;
3. built-in default.

For example, this environment value overrides only the Qwen entry while other
YAML settings remain active:

```powershell
$env:AUTODEVELOP_QWEN_MODEL = "qwen3-vl-32b-instruct"
```

To use a different YAML file:

```powershell
$env:AUTODEVELOP_CONFIG_FILE = "D:\AutoDevelop\my-models.yaml"
```

Relative custom paths are resolved from the AutoDevelop AI application root,
not the current console directory. The active `config/models.yaml` is ignored
by Git; commit only `config/models.example.yaml`.

YAML configuration is loaded once during backend startup. Restart the
AutoDevelop AI backend after changing the YAML file. Automatic reload and file
watching are not enabled.

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
`http://127.0.0.1:1234/v1`. The current client provides generic model-listing
and JSON-completion operations; no vision prompt is included.

ExifTool defaults to the `exiftool` executable on `PATH`. Override
`AUTODEVELOP_EXIFTOOL_PATH` when it is installed elsewhere.

## Run tests

```powershell
python -m pytest
```

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
- Log: `logs/autodevelop.log`
- Temporary previews: `temp/`
