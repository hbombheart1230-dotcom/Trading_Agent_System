from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _configure_repo_pycache_prefix() -> None:
    if os.getenv("PYTHONPYCACHEPREFIX"):
        return
    if getattr(sys, "pycache_prefix", None):
        return
    repo_root = _repo_root()
    sys.pycache_prefix = str(repo_root / "__pycache__")


_configure_repo_pycache_prefix()
