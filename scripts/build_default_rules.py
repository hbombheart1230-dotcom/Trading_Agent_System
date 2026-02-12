#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build default rules from kiwoom_api_list_tagged.jsonl")
    ap.add_argument("--in", dest="inp", default="data/specs/kiwoom_api_list_tagged.jsonl", help="Input tagged jsonl")
    ap.add_argument("--out", dest="out", default="data/specs/default_rules.json", help="Output rules json")
    args = ap.parse_args()

    inp = Path(args.inp)
    out = Path(args.out)

    if not inp.exists():
        print(f"[ERR] input not found: {inp}")
        return 2

    # Tag-based grouping
    prefix_defaults: Dict[str, Dict[str, Any]] = {}
    api_overrides: Dict[str, Dict[str, Any]] = {}

    # Sensible domain defaults keyed by tags (you can extend tags freely)
    TAG_DEFAULTS: Dict[str, Dict[str, Any]] = {
        "account": {"stk_bond_tp": "1", "sell_tp": "0"},
        "order_status": {"mrkt_tp": "0"},
        "orders": {"trde_tp": "3", "cond_uv": ""},
        "domestic": {"dmst_stex_tp": "KRX"},
    }

    # Prefix heuristics (very stable)
    PREFIX_DEFAULTS: Dict[str, Dict[str, Any]] = {
        "kt000": {"stk_bond_tp": "1", "sell_tp": "0"},
        "kt100": {"dmst_stex_tp": "KRX", "trde_tp": "3", "cond_uv": ""},
        "ka100": {},  # market info; usually needs stk_cd
    }

    # Build from records
    n = 0
    for rec in iter_jsonl(inp):
        n += 1
        api_id = str(rec.get("api_id") or rec.get("id") or "").strip()
        if not api_id:
            continue
        tags = rec.get("tags") or rec.get("tag") or []
        if isinstance(tags, str):
            tags = [tags]
        tags = [str(t).strip() for t in tags if str(t).strip()]

        # Start with prefix rules
        for pref, d in PREFIX_DEFAULTS.items():
            if api_id.startswith(pref):
                prefix_defaults.setdefault(pref, {}).update(d)

        # Apply tag defaults to api overrides
        merged: Dict[str, Any] = {}
        for t in tags:
            if t in TAG_DEFAULTS:
                merged.update(TAG_DEFAULTS[t])

        # Special cases: a few APIs are known to have hard requirements
        if api_id == "kt00009":
            merged.setdefault("mrkt_tp", "0")
        if api_id in ("kt10000", "kt10001"):
            merged.setdefault("dmst_stex_tp", "KRX")
            merged.setdefault("trde_tp", "3")
            merged.setdefault("cond_uv", "")
        if api_id == "kt00007":
            merged.setdefault("qry_tp", "2")

        if merged:
            api_overrides[api_id] = {**api_overrides.get(api_id, {}), **merged}

    # Normalize: for kt100* market order implies ord_uv empty (engine will enforce too)
    rules = {
        "version": 1,
        "generated_from": str(inp),
        "generated_at": __import__("datetime").datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "prefix_defaults": prefix_defaults,
        "api_overrides": api_overrides,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Built rules: {out} (records={n}, api_overrides={len(api_overrides)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
