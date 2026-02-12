# libs/api_catalog.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union
import json


class ApiCatalogError(Exception):
    """Base error for API catalog."""


class ApiNotFoundError(ApiCatalogError):
    """Raised when an API id does not exist in catalog."""


class ApiCatalogLoadError(ApiCatalogError):
    """Raised when catalog cannot be loaded or parsed."""


@dataclass(frozen=True)
class ApiSpec:
    """
    Minimal API specification record.

    You can extend fields later without breaking callers by keeping
    `extra` for arbitrary metadata.
    """
    api_id: str
    title: str = ""
    description: str = ""
    method: str = ""
    path: str = ""
    tags: List[str] = None
    params: Dict[str, Any] = None
    extra: Dict[str, Any] = None

    def __post_init__(self):
        object.__setattr__(self, "tags", self.tags or [])
        object.__setattr__(self, "params", self.params or {})
        object.__setattr__(self, "extra", self.extra or {})

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ApiSpec":
        # allow flexible keys
        api_id = d.get("api_id") or d.get("id") or d.get("apiId")
        if not api_id or not isinstance(api_id, str):
            raise ApiCatalogLoadError(f"Invalid api_id in record: {d}")

        return ApiSpec(
            api_id=api_id,
            title=str(d.get("title", "")),
            description=str(d.get("description", "")),
            method=str(d.get("method", "")),
            path=str(d.get("path", "")),
            tags=list(d.get("tags", []) or []),
            params=dict(d.get("params", {}) or {}),
            extra={k: v for k, v in d.items() if k not in {
                "api_id", "id", "apiId", "title", "description", "method", "path", "tags", "params"
            }},
        )


class ApiCatalog:
    """
    Central registry for API specs.

    Supports loading from:
      - dict/list object
      - JSON file (list or dict mapping)
      - JSONL file (one JSON object per line)

    Designed so later you can plug Excel/Sheet loader behind this interface
    without changing callers.
    """

    def __init__(self, specs: Iterable[ApiSpec]):
        self._by_id: Dict[str, ApiSpec] = {}
        for s in specs:
            if s.api_id in self._by_id:
                raise ApiCatalogLoadError(f"Duplicated api_id: {s.api_id}")
            self._by_id[s.api_id] = s

    def get(self, api_id: str) -> ApiSpec:
        try:
            return self._by_id[api_id]
        except KeyError:
            raise ApiNotFoundError(f"API not found: {api_id}") from None

    def has(self, api_id: str) -> bool:
        return api_id in self._by_id

    def list_ids(self) -> List[str]:
        return sorted(self._by_id.keys())

    def list_specs(self) -> List[ApiSpec]:
        return [self._by_id[k] for k in self.list_ids()]

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        # convenient for debugging/export
        out: Dict[str, Dict[str, Any]] = {}
        for api_id, spec in self._by_id.items():
            out[api_id] = {
                "api_id": spec.api_id,
                "title": spec.title,
                "description": spec.description,
                "method": spec.method,
                "path": spec.path,
                "tags": list(spec.tags),
                "params": dict(spec.params),
                **dict(spec.extra),
            }
        return out

    @staticmethod
    def from_obj(obj: Union[Dict[str, Any], List[Dict[str, Any]]]) -> "ApiCatalog":
        specs: List[ApiSpec] = []
        if isinstance(obj, dict):
            # allow mapping style: { "API001": {...}, ... }
            # or container style: { "apis": [ ... ] }
            if "apis" in obj and isinstance(obj["apis"], list):
                for rec in obj["apis"]:
                    specs.append(ApiSpec.from_dict(rec))
            else:
                for api_id, rec in obj.items():
                    if isinstance(rec, dict):
                        rec = dict(rec)
                        rec.setdefault("api_id", api_id)
                        specs.append(ApiSpec.from_dict(rec))
        elif isinstance(obj, list):
            for rec in obj:
                if not isinstance(rec, dict):
                    raise ApiCatalogLoadError("Catalog list must contain dict records.")
                specs.append(ApiSpec.from_dict(rec))
        else:
            raise ApiCatalogLoadError(f"Unsupported catalog object type: {type(obj)}")

        return ApiCatalog(specs)

    @staticmethod
    def load(path: Union[str, Path]) -> "ApiCatalog":
        p = Path(path)
        if not p.exists():
            raise ApiCatalogLoadError(f"Catalog file not found: {p}")

        if p.suffix.lower() == ".jsonl":
            specs: List[ApiSpec] = []
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    specs.append(ApiSpec.from_dict(json.loads(line)))
            except Exception as e:
                raise ApiCatalogLoadError(f"Failed to parse JSONL: {p} ({e})") from e
            return ApiCatalog(specs)

        # default: json
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            raise ApiCatalogLoadError(f"Failed to parse JSON: {p} ({e})") from e

        return ApiCatalog.from_obj(obj)
