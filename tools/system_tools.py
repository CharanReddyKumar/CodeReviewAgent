from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ToolResult:
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    error: Optional[str] = None


def command_available(executable: str) -> bool:
    return shutil.which(executable) is not None


def run_command(command: List[str], cwd: Path, *, timeout: Optional[float] = None) -> ToolResult:
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return ToolResult(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
        )
    except FileNotFoundError as exc:
        return ToolResult(
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            error=str(exc),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return ToolResult(
            command=command,
            returncode=124,
            stdout=stdout.strip(),
            stderr=stderr.strip(),
            error=f"Command timed out after {timeout} seconds",
        )
