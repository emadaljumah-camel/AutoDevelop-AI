import subprocess
from pathlib import Path

import pytest

from autodevelop.media.exif import ExifToolClient, ExifToolError


def test_extract_metadata_uses_temporary_image(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preview_dir = tmp_path / "previews"

    def fake_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        image_path = Path(command[-1])
        assert image_path.read_bytes() == b"image-data"
        assert command[:3] == ["custom-exiftool", "-json", "-n"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='[{"SourceFile": "preview.jpg", "ISO": 400}]',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = ExifToolClient(
        executable="custom-exiftool",
        temp_dir=preview_dir,
    )

    metadata = client.extract_metadata(b"image-data", "photo.raw")

    assert metadata == {"ISO": 400}
    assert list(preview_dir.iterdir()) == []


def test_extract_metadata_reports_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="not-json",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = ExifToolClient("exiftool", tmp_path)

    with pytest.raises(ExifToolError, match="invalid JSON"):
        client.extract_metadata(b"image-data", "photo.jpg")


def test_extract_metadata_reports_missing_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(*_: object, **__: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = ExifToolClient("missing-exiftool", tmp_path)

    with pytest.raises(ExifToolError, match="missing-exiftool"):
        client.extract_metadata(b"image-data", "photo.jpg")
