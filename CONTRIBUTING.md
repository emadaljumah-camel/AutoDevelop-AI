# Contributing

AutoDevelop AI is an experimental Lightroom Classic plug-in and Python backend.
Discuss substantial behavior or architecture changes in an issue before opening
a pull request. Keep changes focused and preserve unrelated work.

## Development setup

Follow the [README setup](README.md#setup) using Python 3.12. Install editable
development dependencies with `python -m pip install -e ".[test]"`. Run commands
from the repository root. Tests use fake clients and HTTP mocks; a running
Lightroom installation, model server, or cloud API key is not required.

```powershell
python -m pytest -q
git diff --check
```

Install Lua 5.1 or LuaJIT to run the standalone plug-in harness through pytest.
If it is not on PATH, set `AUTODEVELOP_LUA` to its executable path. Without a
runtime, pytest reports that check as skipped. CI runs it with Lua 5.1.

## Pull requests

- Describe the problem, resulting behavior, and tests performed.
- Add focused tests for behavior changes, including failed requests and recovery
  when changing durable jobs or photo application.
- Update documentation when setup, configuration, retention, or behavior changes.
- Identify manual Lightroom checks separately from automated test results.
- Use a disposable catalog or backed-up test photos for manual checks.
- Do not commit API keys, local configuration, photos, catalogs, job folders,
  learning databases, logs, or model weights. Use synthetic fixtures.
- Sanitize paths, filenames, image metadata, and diagnostic output before posting.

Contributions are submitted under the repository's [MIT license](LICENSE).
Include attribution and compatible licensing for any third-party material.
Report security issues using [SECURITY.md](SECURITY.md), not a public issue.
