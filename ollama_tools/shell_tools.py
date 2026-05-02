"""Local shell command helpers."""

from __future__ import annotations

import subprocess
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


def run_local_command(command: str, cwd: str | None = None, timeout: int = 60) -> CommandResult:
    require_tool("local_command")
    validate_command(command)
    base = get_work_dir().resolve()
    working_dir_path = Path(cwd).expanduser().resolve() if cwd else base
    if is_deploy_mode() and not get_dangerous_mode():
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
