# scripts/build_api_catalog.py
from __future__ import annotations

from pathlib import Path
import json
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

INPUT_FILES = [
    Path("data/specs/kiwoom_api_list_tagged.jsonl"),
    Path("data/specs/kiwoom_apis.jsonl"),
]

OUTPUT_FILE = Path("data/specs/api_catalog.jsonl")


def load_jsonl(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


def _yn(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("y", "yes", "true", "1")


def _coerce_params_from_kiwoom_apis(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert kiwoom_apis.jsonl's structure:
      rec["request"]["header"] : [{element, required, ...}]
      rec["request"]["body"]   : [{element, required, ...}]
    into ApiSpec.params schema shape 2:
      {"header":[{"name":..., "required":... , ...}], "body":[...], "query":[...]}
    """
    req = rec.get("request") or {}
    hdr = req.get("header") or []
    body = req.get("body") or []

    def conv(items: List[Dict[str, Any]], loc: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            name = it.get("element") or it.get("name") or it.get("field")
            if not name:
                continue
            out.append({
                "name": str(name),
                "required": _yn(it.get("required")),
                "type": it.get("type", ""),
                "length": it.get("length", ""),
                "description": it.get("description", "") or it.get("name_ko", ""),
                "source": "kiwoom_apis",
                "in": loc,
            })
        return out

    params: Dict[str, Any] = {}
    if hdr:
        params["header"] = conv(hdr, "header")

    # Kiwoom REST 대부분 POST/GET이지만, GET이면 body 항목을 query로 취급하는 편이 자연스러움
    method = (rec.get("method") or rec.get("http_method") or "").upper()
    if body:
        if method == "GET":
            params["query"] = conv(body, "query")
        else:
            params["body"] = conv(body, "body")

    return params


def merge_records(records: list[dict]) -> dict:
    out = {
        "api_id": records[0]["api_id"],
        "title": "",
        "description": "",
        "method": "",
        "path": "",
        "tags": [],
        "params": {},  # <-- enriched
        "_sources": [],
        "_flags": {
            "callable": True,
            "merged": len(records) > 1,
        },
    }

    for r in records:
        # Normalize known field variants from Kiwoom source jsonl
        # - kiwoom_apis.jsonl: name/desc/http_method/endpoint
        if not r.get("title") and r.get("name"):
            r["title"] = r.get("name")
        if not r.get("description") and r.get("desc"):
            r["description"] = r.get("desc")
        if not r.get("method") and r.get("http_method"):
            r["method"] = r.get("http_method")
        if not r.get("path") and r.get("endpoint"):
            r["path"] = r.get("endpoint")

        # Prefer endpoint from kiwoom_apis.jsonl if present
        if not r.get("path") and r.get("endpoint"):
            r["path"] = r["endpoint"]

        for k in ("title", "description", "method", "path"):
            if not out[k] and r.get(k):
                out[k] = r[k]

        if "tags" in r and isinstance(r["tags"], list):
            out["tags"].extend(t for t in r["tags"] if t not in out["tags"])

        # 1) If already has params (future-proof)
        if "params" in r and isinstance(r["params"], dict) and r["params"]:
            out["params"].update(r["params"])

        # 2) If it's a kiwoom_apis.jsonl record, synthesize params from request schema
        if "request" in r and isinstance(r.get("request"), dict):
            synthesized = _coerce_params_from_kiwoom_apis(r)
            # merge by location key (header/query/body)
            for loc, lst in synthesized.items():
                if loc not in out["params"]:
                    out["params"][loc] = []
                # de-dup by name
                existing = {x.get("name") for x in out["params"].get(loc, []) if isinstance(x, dict)}
                for item in lst:
                    if item.get("name") not in existing:
                        out["params"][loc].append(item)

        src = r.get("_source")
        if src and src not in out["_sources"]:
            out["_sources"].append(src)

        if r.get("_flags", {}).get("callable") is False:
            out["_flags"]["callable"] = False

    return out


def main():
    bucket: dict[str, list[dict]] = defaultdict(list)

    for src in INPUT_FILES:
        for rec in load_jsonl(src):
            api_id = rec.get("api_id")
            if not api_id:
                continue
            rec["_source"] = src.name
            bucket[api_id].append(rec)

    merged = [merge_records(recs) for recs in bucket.values()]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[OK] Built {len(merged)} API records → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
