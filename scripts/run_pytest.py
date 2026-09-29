from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    python_exe = repo_root / "venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        raise FileNotFoundError(f"Python executable not found: {python_exe}")

    for arg in argv:
        if arg == "--basetemp" or arg.startswith("--basetemp="):
            raise SystemExit(
                "Do not pass --basetemp. conftest.py::pytest_configure owns it exclusively, pointing "
                "pytest's temp output at an OS-temp, per-process directory so it never accumulates inside this repo."
            )

    cmd = [str(python_exe), "-m", "pytest", *argv]
    completed = subprocess.run(cmd, cwd=repo_root)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
