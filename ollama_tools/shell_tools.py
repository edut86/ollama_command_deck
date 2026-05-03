"""Local shell command helpers."""

from __future__ import annotations

import subprocess
import shlex
from dataclasses import dataclass
from pathlib import Path

from .config import get_dangerous_mode, get_work_dir, is_deploy_mode
from .safety import validate_command
from .tool_registry import require_tool


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str


def _path_token_inside_base(token: str, base: Path) -> bool:
    path = Path(token).expanduser()
    if not path.is_absolute():
        if token == ".." or token.startswith("../") or "/../" in token:
            return False
        return True
    try:
        path.resolve().relative_to(base)
    except ValueError:
        return False
    return True


def validate_command_paths_inside_work_dir(command: str, base: Path | None = None) -> None:
    """Reject obvious shell path escapes from the configured work directory."""
    resolved_base = (base or get_work_dir()).resolve()
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Could not parse shell command safely: {exc}") from exc
    for token in tokens:
        if token.startswith("-"):
            continue
        if token.startswith("/") or token.startswith("~") or token == ".." or token.startswith("../") or "/../" in token:
            if not _path_token_inside_base(token, resolved_base):
                raise ValueError(f"Builder local commands must stay inside configured work directory: {resolved_base}")


def run_local_command(
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
    enforce_work_dir: bool = False,
) -> CommandResult:
    require_tool("local_command")
    validate_command(command)
    base = get_work_dir().resolve()
    working_dir_path = Path(cwd).expanduser().resolve() if cwd else base
    if enforce_work_dir:
        validate_command_paths_inside_work_dir(command, base)
    if enforce_work_dir or (is_deploy_mode() and not get_dangerous_mode()):
        try:
            working_dir_path.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"cwd must stay inside configured work directory: {base}") from exc
    working_dir = str(working_dir_path)
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=working_dir,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(command, proc.returncode, proc.stdout, proc.stderr)
