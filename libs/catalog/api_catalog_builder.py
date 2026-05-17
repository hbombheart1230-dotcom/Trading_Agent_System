from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

INPUT_FILES = [
    Path("data/specs/kiwoom_api_list_tagged.jsonl"),
    Path("data/specs/kiwoom_apis.jsonl"),
]

OUTPUT_FILE = Path("data/specs/api_catalog.jsonl")


def load_jsonl(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def _yn(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("y", "yes", "true", "1")


def _coerce_params_from_kiwoom_apis(rec: Dict[str, Any]) -> Dict[str, Any]:
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
            out.append(
                {
                    "name": str(name),
                    "required": _yn(it.get("required")),
                    "type": it.get("type", ""),
                    "length": it.get("length", ""),
                    "description": it.get("description", "") or it.get("name_ko", ""),
                    "source": "kiwoom_apis",
                    "in": loc,
                }
            )
        return out

    params: Dict[str, Any] = {}
    if hdr:
        params["header"] = conv(hdr, "header")

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
        "params": {},
        "_sources": [],
        "_flags": {
            "callable": True,
            "merged": len(records) > 1,
        },
    }

    for r in records:
        if not r.get("title") and r.get("name"):
            r["title"] = r.get("name")
        if not r.get("description") and r.get("desc"):
            r["description"] = r.get("desc")
        if not r.get("method") and r.get("http_method"):
            r["method"] = r.get("http_method")
        if not r.get("path") and r.get("endpoint"):
            r["path"] = r.get("endpoint")

        for key in ("title", "description", "method", "path"):
            if not out[key] and r.get(key):
                out[key] = r[key]

        if "tags" in r and isinstance(r["tags"], list):
            out["tags"].extend(tag for tag in r["tags"] if tag not in out["tags"])

        if "params" in r and isinstance(r["params"], dict) and r["params"]:
            out["params"].update(r["params"])

        if "request" in r and isinstance(r.get("request"), dict):
            synthesized = _coerce_params_from_kiwoom_apis(r)
            for loc, items in synthesized.items():
                out["params"].setdefault(loc, [])
                existing = {x.get("name") for x in out["params"].get(loc, []) if isinstance(x, dict)}
                for item in items:
                    if item.get("name") not in existing:
                        out["params"][loc].append(item)

        source = r.get("_source")
        if source and source not in out["_sources"]:
            out["_sources"].append(source)

        if r.get("_flags", {}).get("callable") is False:
            out["_flags"]["callable"] = False

    return out


def build_api_catalog(
    *,
    input_files: Optional[Iterable[Path]] = None,
    output_file: Optional[Path] = None,
) -> Path:
    bucket: dict[str, list[dict]] = defaultdict(list)
    sources = list(input_files or INPUT_FILES)
    target = Path(output_file or OUTPUT_FILE)

    for src in sources:
        for rec in load_jsonl(src):
            api_id = rec.get("api_id")
            if not api_id:
                continue
            rec["_source"] = src.name
            bucket[api_id].append(rec)

    merged = [merge_records(recs) for recs in bucket.values()]

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in merged:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"[OK] Built {len(merged)} API records -> {target}")
    return target


def main() -> None:
    build_api_catalog()


if __name__ == "__main__":
    main()
