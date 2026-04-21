from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


def first_universe_symbol(env: Mapping[str, Any] | None = None) -> str:
    source = env if isinstance(env, Mapping) else os.environ
    raw = str(source.get("UNIVERSE_SYMBOLS", "") or "").strip()
    if not raw:
        return ""
    for part in raw.split(","):
        symbol = str(part or "").strip()
        if symbol:
            return symbol
    return ""


def to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def to_bool(value: Any, default: bool = False) -> bool:
    raw = str(value if value is not None else "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "y", "on"}


def normalize_tick_pipeline(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"integrated_chain", "integrated", "chain"}:
        return "integrated_chain"
    return "legacy_m10"


def resolve_env_path(root: Path, argv: Optional[Sequence[str]], *, env_var: str = "ENV_PATH", default_rel: str = ".env") -> Path:
    args = list(argv or [])
    raw = ""
    for idx, token in enumerate(args):
        cur = str(token or "").strip()
        if not cur:
            continue
        if cur.startswith("--env-path="):
            raw = cur.split("=", 1)[1].strip()
            break
        if cur == "--env-path" and idx + 1 < len(args):
            raw = str(args[idx + 1] or "").strip()
            break
    if not raw:
        raw = str(os.getenv(env_var, "") or "").strip()
    if not raw:
        raw = str(root / default_rel)
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path


def resolve_path_from_root(root: Path, raw: str, default_rel: str) -> Path:
    value = str(raw or "").strip() or str(default_rel)
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path
