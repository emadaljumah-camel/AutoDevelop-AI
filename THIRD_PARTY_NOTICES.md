# Third-party components and external requirements

The [MIT license](LICENSE) covers the original AutoDevelop AI code and
documentation. It does not relicense third-party software, model weights,
services, photographs, or Adobe-generated material.

## Dependencies

Python dependencies are declared in [pyproject.toml](pyproject.toml).
[requirements.txt](requirements.txt) is a version snapshot, not the primary
installation contract. Dependencies retain their own licenses and notices;
review the license metadata and bundled notices for the versions you distribute,
including transitive dependencies. Installing a dependency does not transfer
its copyright to this project.

The project uses FastAPI, HTTPX, Pillow, Pydantic, pydantic-settings, PyYAML,
Uvicorn, and their dependencies. Pytest is used for tests. Lua or LuaJIT is an
external test runtime. CI uses GitHub Actions; their licenses and service terms
remain separate.

## Adobe Lightroom and presets

Adobe Lightroom Classic is proprietary software, installed and licensed
separately. Adobe and Lightroom are trademarks of Adobe. This project is
independent and is not endorsed by Adobe. Compatibility with a Lightroom SDK
version is not a promise that every newer Develop feature works on older hosts.

The maintainer confirms that the three Denoise XMP presets under
[LrPresets/](LrPresets/) were created personally in Adobe Lightroom, rather than
obtained from a third-party preset collection. They contain Lightroom-generated
structures and processing tables; the project's MIT license does not relicense
Adobe software or any underlying Adobe-owned content. Users can also create
the presets in their own Lightroom installation as described in the
[README](README.md#denoise-presets).

## Models and services

Model weights and runtimes are not included. LM Studio, local model families,
and Gemini have separate licenses or service terms. Users must obtain suitable
vision-capable models and check their permitted uses independently. Example
model identifiers are configuration examples, not a redistribution grant or
guarantee of availability. Cloud provider usage can incur charges.

ExifTool is an optional external executable used by the metadata-extraction
API. Obtain and license it separately. It is not bundled with this repository.
