# scripts/build_api_catalog.py
from pathlib import Path
import json
from collections import defaultdict

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

        for k in ("title", "description", "method", "path"):
            if not out[k] and r.get(k):
                out[k] = r[k]

        if "tags" in r and isinstance(r["tags"], list):
            out["tags"].extend(t for t in r["tags"] if t not in out["tags"])

        if "params" in r and isinstance(r["params"], dict):
            out["params"].update(r["params"])

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
