from __future__ import annotations

import os
import subprocess
from typing import Any


def hidden_creationflags() -> int:
    flags = 0
    flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    return int(flags)


def background_creationflags() -> int:
    flags = int(hidden_creationflags())
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= int(getattr(subprocess, name, 0) or 0)
    return int(flags)


def with_hidden_creationflags(kwargs: dict[str, Any] | None = None, *, background: bool = False) -> dict[str, Any]:
    out = dict(kwargs or {})
    if os.name == "nt" and "creationflags" not in out:
        out["creationflags"] = background_creationflags() if background else hidden_creationflags()
    return out


def run_hidden(*popenargs: Any, background: bool = False, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(*popenargs, **with_hidden_creationflags(kwargs, background=background))


def popen_hidden(*popenargs: Any, background: bool = False, **kwargs: Any) -> subprocess.Popen[Any]:
    return subprocess.Popen(*popenargs, **with_hidden_creationflags(kwargs, background=background))


__all__ = [
    "background_creationflags",
    "hidden_creationflags",
    "popen_hidden",
    "run_hidden",
    "with_hidden_creationflags",
]
