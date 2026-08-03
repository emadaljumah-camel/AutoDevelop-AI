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
roll using reliable horizons or structural lines. Transform Upright is a third,
independent categorical decision and is never simulated with `CropAngle`.
Lightroom combines accepted crop and rotational-leveling geometry only at
application time.

HDR Edit Mode is also a first-class categorical decision. It is selected from
current scene evidence, model confidence, optional global HDR feedback, and the
Lightroom preference. HDR is not enabled or disabled by the selected style
profile. RAW eligibility, Lightroom capability, workflow, dynamic-range, noise,
and exposure safeguards remain authoritative.

AI Denoise is a technical RAW-processing decision rather than a Develop
slider. ISO 3200 through 6399 proactively selects amount 50, ISO 6400 and above
selects 75, and ISO 1600 through 3199 selects 25 when scene analysis also
reports high noise. Lower-confidence model recommendations still pass through
the selected profile's ISO, confidence, and maximum-amount safeguards. The
validated amount is quantized to a verified preset without exceeding the
profile maximum.

The Lightroom plug-in applies Denoise through native Develop presets so that
Lightroom generates its photo-specific AI `FilterList`. Create these presets
in Lightroom with only the Denoise/AI Edit setting selected:

- `AutoDevelop AI - Denoise 25`
- `AutoDevelop AI - Denoise 50`
- `AutoDevelop AI - Denoise 75`

Only the preset required by a recommendation must exist. Denoise is prepared
only for supported RAW or DNG sources with a restorable current state. The
preset is applied before ordinary Develop settings; a combined apply failure
restores both the original Develop values and the captured Denoise state.
Missing presets and unsupported sources produce visible warnings instead of
silently claiming Denoise was applied.

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

On Windows, the repository launcher validates the virtual environment, starts
the backend from the project root, and preserves the server exit code:

```powershell
.\start-backend.bat
```

The equivalent direct command is:

```powershell
uvicorn autodevelop.main:app --app-dir backend --host 127.0.0.1 --port 8005
```

The health endpoint is available at:

```text
GET http://127.0.0.1:8005/autodevelop/v1/health
```

### Lightroom on another computer

The Lightroom plug-in uploads each temporary 1600-pixel JPEG preview in the
request as `preview_base64`. It never sends the Lightroom computer's local
temporary path to the backend. The backend retains `preview_path` only for
backward-compatible API clients.

Base64 expands binary content by approximately one third. The plug-in rejects
a preview above 8 MiB before encoding, rejects an estimated or actual encoded
payload above 11 MiB, and still deletes the per-photo temporary JPEG through
the normal cleanup path. Preview content and local paths are not written to
ordinary logs or learning records.

To keep the backend and LM Studio on one computer while Lightroom runs on
another computer on the same private LAN:

1. Copy the complete `AutoDevelopAI.lrplugin` directory to the Lightroom
   computer and add it through **File > Plug-in Manager**.
2. Start the backend on the backend computer with an explicit LAN bind:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn autodevelop.main:app `
       --app-dir backend --host 0.0.0.0 --port 8005
   ```

3. Permit inbound TCP port 8005 in Windows Firewall only on the Private
   profile and preferably only from the Lightroom computer's IP address.
4. Do not expose LM Studio port 1234. It remains bound to
   `127.0.0.1:1234` for backend-only access.
5. On the Lightroom computer, verify
   `http://BACKEND-LAN-IP:8005/autodevelop/v1/health`, then set **Backend
   URL** in the plug-in preferences to `http://BACKEND-LAN-IP:8005` without
   the API suffix.
6. Keep the request timeout high enough for the Base64 upload plus inference.
   The default is 120 seconds; the plug-in accepts 10 through 600 seconds.
7. Create or import the three native Denoise presets on the Lightroom
   computer if Denoise 25, 50, and 75 should all be available.

Verify a deployment by running Analyze and Auto Develop on one photo, checking
that the backend receives `preview_base64` and no `preview_path`, and confirming
that the Lightroom temporary preview is removed afterward. Port 8005 must not
be exposed directly to the public internet because this API does not provide
transport encryption or client authentication.

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
Feedback**. The command first requests a read-only comparison preview, then
saves feedback only after confirmation. A failed preview does not consume the
pending baseline and can be retried.

After at least three similar usable examples, future Develop requests may
receive compact aggregate preferences. Slider, crop, rotational-leveling, and
Upright preferences are scoped to the effective style. HDR feedback is
retrieved globally because HDR is based on scene need rather than style.

Learning does not fine-tune models, monitor Lightroom in the background, or
upload data. AI Denoise application is not learned as a numeric Develop
slider. Its SQLite database defaults to
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
