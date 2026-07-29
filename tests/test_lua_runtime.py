"""Run the standalone Lua checks when a compatible interpreter is available."""

from collections.abc import Callable
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LUA_HARNESS = REPOSITORY_ROOT / "tests" / "lua" / "run_tests.lua"
LUA_EXECUTABLE_NAMES = ("lua", "lua5.1", "lua51", "luajit")


def _without_matching_outer_quotes(value: str) -> str:
    if (
        len(value) >= 2
        and value[0] in {'"', "'"}
        and value[-1] == value[0]
    ):
        return value[1:-1]
    return value


def _split_command(value: str) -> list[str]:
    return shlex.split(value, posix=os.name != "nt")


def _parse_configured_lua_command(
    configured: str,
    *,
    is_file: Callable[[str], bool],
) -> list[str]:
    """Parse an interpreter path plus optional arguments without a shell."""

    value = configured.strip()
    if not value:
        return []

    entire_value = _without_matching_outer_quotes(value)
    if is_file(entire_value):
        return [entire_value]

    if value[0] in {'"', "'"}:
        quote = value[0]
        closing_quote = value.find(quote, 1)
        if closing_quote < 0:
            pytest.fail("AUTODEVELOP_LUA contains an unmatched executable quote")

        executable = value[1:closing_quote]
        remainder = value[closing_quote + 1 :].strip()
        arguments = _split_command(remainder) if remainder else []
        return [executable, *arguments]

    whitespace_positions = [
        index for index, character in enumerate(value) if character.isspace()
    ]
    for position in reversed(whitespace_positions):
        executable = value[:position].rstrip()
        if executable and is_file(executable):
            remainder = value[position:].strip()
            arguments = _split_command(remainder) if remainder else []
            return [executable, *arguments]

    return _split_command(value)


def _configured_lua_command() -> list[str] | None:
    configured = os.environ.get("AUTODEVELOP_LUA", "").strip()
    if not configured:
        return None

    command = _parse_configured_lua_command(
        configured,
        is_file=lambda candidate: Path(candidate).is_file(),
    )
    if not command:
        pytest.fail("AUTODEVELOP_LUA did not contain an executable")

    executable = shutil.which(command[0])
    if executable is None and Path(command[0]).is_file():
        executable = str(Path(command[0]).resolve())
    if executable is None:
        pytest.fail(
            "AUTODEVELOP_LUA does not identify an available Lua interpreter: "
            f"{command[0]}"
        )
    command[0] = executable
    return command


@pytest.mark.parametrize(
    ("configured", "existing_paths", "expected"),
    [
        (
            r"C:\Program Files\Lua\lua.exe",
            {r"C:\Program Files\Lua\lua.exe"},
            [r"C:\Program Files\Lua\lua.exe"],
        ),
        (
            r'"C:\Program Files\Lua\lua.exe"',
            {r"C:\Program Files\Lua\lua.exe"},
            [r"C:\Program Files\Lua\lua.exe"],
        ),
        (
            r'"C:\Program Files\Lua\lua.exe" -E',
            {r"C:\Program Files\Lua\lua.exe"},
            [r"C:\Program Files\Lua\lua.exe", "-E"],
        ),
        (
            r"C:\Tools\lua.exe -E",
            {r"C:\Tools\lua.exe"},
            [r"C:\Tools\lua.exe", "-E"],
        ),
        ("lua", set(), ["lua"]),
    ],
)
def test_parse_configured_lua_command(
    configured: str,
    existing_paths: set[str],
    expected: list[str],
) -> None:
    command = _parse_configured_lua_command(
        configured,
        is_file=existing_paths.__contains__,
    )

    assert command == expected
    assert all('"' not in argument and "'" not in argument for argument in command)


def test_configured_lua_command_returns_none_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTODEVELOP_LUA", raising=False)

    assert _configured_lua_command() is None


def test_configured_lua_command_resolves_simple_path_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTODEVELOP_LUA", "lua")
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: r"C:\Lua\lua.exe" if name == "lua" else None,
    )

    assert _configured_lua_command() == [r"C:\Lua\lua.exe"]


def test_configured_lua_command_rejects_missing_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTODEVELOP_LUA", "missing-autodevelop-lua")
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    with pytest.raises(
        pytest.fail.Exception,
        match="does not identify an available Lua interpreter",
    ):
        _configured_lua_command()


def _discover_lua_command() -> list[str] | None:
    configured = _configured_lua_command()
    if configured is not None:
        return configured

    for name in LUA_EXECUTABLE_NAMES:
        executable = shutil.which(name)
        if executable is not None:
            return [executable]
    return None


def test_lua_harness() -> None:
    """Fail on Lua assertion errors, or skip clearly when Lua is unavailable."""

    command = _discover_lua_command()
    if command is None:
        pytest.skip(
            "Lua runtime checks skipped: set AUTODEVELOP_LUA or install "
            "lua/lua5.1/lua51/luajit on PATH"
        )

    result = subprocess.run(
        [*command, str(LUA_HARNESS)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )
    assert result.returncode == 0, (
        f"Lua harness failed with exit code {result.returncode}\n{output}"
    )
    assert "Lua assertions passed:" in result.stdout


def test_lua_harness_invokes_subprocess_with_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTODEVELOP_LUA", "lua -E")
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: name if name == "lua" else None,
    )
    invocation: dict[str, object] = {}

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        invocation["command"] = command
        invocation["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Lua assertions passed: 1\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    test_lua_harness()

    assert invocation["command"] == ["lua", "-E", str(LUA_HARNESS)]
    assert isinstance(invocation["command"], list)
    assert "shell" not in invocation["kwargs"]
