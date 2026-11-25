# AutoDevelop AI

AutoDevelop AI is an experimental Lightroom Classic automation project composed of:

- the `AutoDevelopAI.lrplugin` Lightroom Classic Lua plug-in;
- a Python 3.12 FastAPI backend;
- an LM Studio-compatible model client;
- file-based JSON style profiles;
- SQLite edit-session storage; and
- backend and integration tests.

The plug-in supports Analyze, validated Auto Develop, style and model
selection, production preferences, and optional local personalized learning.

Version 0.1.x requires manual testing in your Lightroom version. Back up your
catalog and test with disposable photos before applying changes to important
work. AI recommendations can be wrong. The backend has no client authentication
or built-in TLS; see [security and privacy](SECURITY.md).

Local inference is the default. Selecting the optional Gemini provider sends
previews and prompts to Google's API and may incur charges. Model weights,
Lightroom, and inference runtimes are not included.

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

AutoDevelop AI recommends only Upright Off, Auto, or Level. Lightroom Full and
Vertical remain readable for existing photo metadata and historical learning
records, but they are excluded from prompts, profile policies, personalization,
and final recommendations.

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

### Denoise presets

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
- Lightroom Classic, installed and licensed separately. The plug-in declares
  SDK 13.0 and minimum SDK 6.0; recent HDR and Denoise features require a
  compatible host and source photo. This is not a tested compatibility matrix.
- LM Studio or another OpenAI-compatible server with a suitable vision-capable
  model, or an explicitly configured Gemini account/API key. Hardware
  requirements depend on your chosen runtime and model.
- ExifTool on PATH if using the backend's metadata-extraction API
- Lua 5.1 or LuaJIT to include the standalone plug-in test harness

## Setup

```powershell
git clone https://github.com/emadaljumah-camel/AutoDevelop-AI.git
cd AutoDevelop-AI
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Run commands from the repository root. Copy examples only on first setup;
preserve an existing local configuration. [pyproject.toml](pyproject.toml)
defines the installation dependencies; [requirements.txt](requirements.txt)
is a version snapshot.

## Configure AI models

Copy the committed example to create a machine-local active configuration:

```powershell
Copy-Item config\models.example.yaml config\models.yaml
```

Edit provider model identifiers to match the models exposed by the configured
inference provider:

Start the inference server and load a vision-capable model yourself. These
identifiers are examples: replace them with exact IDs exposed by your server.
Not every listed model supports images. This setup does not download models.

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

For model/provider settings, environment variables and `.env` entries override
YAML. The copied `.env.example` includes model IDs and a default model: update
those values too, or remove the corresponding entries from your local `.env`
to let YAML control them. Keep credentials in the environment or `.env`.

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

Without activating the virtual environment, prefix that command with
`.\.venv\Scripts\python.exe -m`. The launcher explicitly binds loopback and
port 8005; environment host/port values do not override its command arguments.

The health endpoint is available at:

```text
GET http://127.0.0.1:8005/autodevelop/v1/health
```

A healthy API does not prove that the selected model is loaded or can process
images. Test **Analyze Selected Photos** on one photo to verify inference.

### Install and use the Lightroom plug-in

1. Open **File > Plug-in Manager** in Lightroom Classic and add the complete
   [AutoDevelopAI.lrplugin/](AutoDevelopAI.lrplugin/) directory.
2. In the plug-in settings, set Backend URL to `http://127.0.0.1:8005`
   without `/autodevelop/v1` when both applications use the same computer.
3. Choose a configured model and style; begin with **Analyze Selected Photos**.
4. Run **Auto Develop Selected Photos** for a durable batch job. Use
   **Check AutoDevelop Job / Apply Results** to recover, review, or apply results.
5. Inspect the applied settings and warnings in Lightroom. Completed inference
   and successful application to the catalog are separate outcomes.

Interrupted jobs retain checkpoints and are marked interrupted after a backend
restart. Check the existing job instead of submitting a duplicate. Cancellation
is cooperative: an active inference request may finish before the runner stops.
It retains job data and does not undo edits already applied.

### Lightroom on another computer

The plug-in renders JPEG previews with a 1600-pixel long-edge limit. Durable
Auto Develop jobs upload binary JPEG bytes to the job preview endpoint.
Synchronous requests such as Analyze use `preview_base64`. The plug-in does not
send its local temporary path as a server-readable preview path. The backend
retains `preview_path` for compatible backend-side API clients.

Base64 expands binary content by approximately one third. The plug-in rejects
a preview above 8 MiB before encoding, rejects an estimated or actual encoded
payload above 11 MiB. Backend durable job previews also default to an 8 MiB
limit. Temporary preview cleanup does not erase durable job storage.

Backend jobs retain previews, manifests, checkpoints, and results in
`data/jobs/`. Lightroom retains durable job material under its configured job
root, which can include catalog paths, filenames, and identifiers. There is no
automatic retention period. Cancellation does not erase stored data. Do not
assume image metadata is stripped. Review [SECURITY.md](SECURITY.md) before
sharing logs, previews, or job artifacts.

To keep the backend and LM Studio on one computer while Lightroom runs on
another computer on a trusted private LAN with restricted client access:

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
6. Keep the request timeout high enough for upload and synchronous inference.
   The default is 120 seconds; the plug-in accepts 10 through 600 seconds.
7. Create or import the three native Denoise presets on the Lightroom
   computer if Denoise 25, 50, and 75 should all be available.

Verify a deployment by running Analyze and Auto Develop on one photo, checking
the appropriate Base64 or binary upload, then reviewing and applying its results.
Check retained durable job files separately from temporary cleanup. Port 8005
must not be exposed directly to the public internet because this API does not provide
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

Tests use fake inference clients and HTTP mocks without cloud credentials or
model weights. The Lua harness is skipped when no interpreter is available;
set `AUTODEVELOP_LUA` or install Lua 5.1/LuaJIT on PATH to include it. CI is
configured for Python 3.12 on Windows and Linux, with a separate Lua 5.1 job.
Automated checks do not exercise the real Lightroom UI or prove model quality.
See [CONTRIBUTING.md](CONTRIBUTING.md) for development instructions.

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

Learning does not fine-tune models or monitor Lightroom in the background.
Storage is local, but aggregate preferences can be included in prompts sent to
the selected provider, including remote providers. AI Denoise application is
not learned as a numeric Develop slider. Its SQLite database defaults to
`data/autodevelop_learning.sqlite3`. See
[docs/LEARNING_SYSTEM.md](docs/LEARNING_SYSTEM.md) for storage, privacy,
configuration, reset, and backup details.

## Project layout

```text
AutoDevelopAI.lrplugin/  Lightroom Classic plug-in
backend/autodevelop/     FastAPI application package
backend/autodevelop/profiles/data/  Bundled JSON style profiles
config/                  Model configuration example and ignored local settings
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
- Durable backend jobs: `data/jobs/`

## License and third-party requirements

Original project code and documentation are available under the
[MIT license](LICENSE). External software, services, model weights, and
Adobe-generated preset material have separate terms; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The maintainer created the
bundled Denoise presets in Lightroom. Users can also create the native presets
in their own Lightroom installation as described above.

Dependency versions have intentionally been preserved. The pinned dependency
snapshot has unresolved security advisories; see
[known dependency advisories](SECURITY.md#known-dependency-advisories).
