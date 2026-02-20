from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.runtime_profile import valid_runtime_profiles
from libs.runtime.runtime_profile import validate_runtime_profile


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _read_env_file(path: str) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    out: Dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if v and v[0] not in ("'", "\"") and "#" in v:
            v = v.split("#", 1)[0].rstrip()
        if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ("'", '"')):
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate runtime profile env policy (M28-1 scaffold).")
    p.add_argument("--profile", choices=list(valid_runtime_profiles()), default=None)
    p.add_argument("--env-path", default=".env")
    p.add_argument("--strict", action="store_true", default=_env_bool("M28_PROFILE_STRICT", False))
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    env_path = str(args.env_path)
    file_env = _read_env_file(env_path)
    effective_env: Dict[str, str] = dict(file_env) if file_env else dict(os.environ)
    profile = str(args.profile or effective_env.get("RUNTIME_PROFILE") or "dev").strip().lower() or "dev"

    out = validate_runtime_profile(
        profile,
        environ=effective_env,
        strict=bool(args.strict),
    )
    out["env_path"] = env_path

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} profile={out['profile']} strict={out['strict']} "
            f"required_missing={len(out['required_missing'])} "
            f"violation_total={len(out['violations'])} warning_total={len(out['warnings'])}"
        )
        for msg in out["required_missing"]:
            print(f"missing_required={msg}")
        for msg in out["violations"]:
            print(f"violation={msg}")
        for msg in out["warnings"]:
            print(f"warning={msg}")

    return 0 if bool(out.get("ok")) else 3


if __name__ == "__main__":
    raise SystemExit(main())
