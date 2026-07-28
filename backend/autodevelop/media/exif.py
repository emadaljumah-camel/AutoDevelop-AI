"""ExifTool-backed image metadata extraction."""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class ExifToolError(RuntimeError):
    """Raised when image metadata cannot be extracted."""


class ExifToolClient:
    """Extract numeric metadata using an external ExifTool executable."""

    def __init__(
        self,
        executable: str,
        temp_dir: Path,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._executable = executable
        self._temp_dir = temp_dir
        self._timeout_seconds = timeout_seconds

    def extract_metadata(
        self,
        image_bytes: bytes,
        filename: str,
    ) -> dict[str, Any]:
        """Extract metadata from image bytes without retaining the image."""

        self._temp_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix or ".jpg"

        with tempfile.TemporaryDirectory(dir=self._temp_dir) as temporary_dir:
            image_path = Path(temporary_dir) / f"preview{suffix}"
            image_path.write_bytes(image_bytes)

            try:
                completed = subprocess.run(
                    [
                        self._executable,
                        "-json",
                        "-n",
                        str(image_path),
                    ],
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=self._timeout_seconds,
                )
            except FileNotFoundError as exc:
                raise ExifToolError(
                    f"ExifTool was not found at {self._executable}"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise ExifToolError(
                    "ExifTool timed out while reading metadata"
                ) from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip() or "ExifTool failed to read metadata"
            raise ExifToolError(detail)

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ExifToolError("ExifTool returned invalid JSON") from exc

        if not payload:
            return {}
        if not isinstance(payload, list) or not isinstance(payload[0], dict):
            raise ExifToolError("ExifTool returned an unexpected response shape")

        metadata: dict[str, Any] = payload[0]
        metadata.pop("SourceFile", None)
        return metadata
