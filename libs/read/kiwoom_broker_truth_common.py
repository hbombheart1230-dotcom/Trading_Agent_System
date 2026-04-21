from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from libs.catalog.api_catalog import ApiCatalog, ApiNotFoundError
from libs.catalog.api_request_builder import PreparedRequest
from libs.core.settings import Settings
from libs.execution.executors.factory import get_executor


def ensure_catalog_path() -> Path:
    catalog_path = Path("data/specs/api_catalog.jsonl")
    if catalog_path.exists():
        return catalog_path
    import scripts.build_api_catalog as bac

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    bac.main()
    return catalog_path


def require_api(catalog: ApiCatalog, api_id: str, title: str) -> str:
    if catalog.has(api_id):
        return api_id
    for spec in catalog.list_specs():
        if (spec.title or "").strip() == title:
            return spec.api_id
    raise ApiNotFoundError(f"Missing API: {api_id} / {title}")


def to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    raw = str(v).strip().replace(",", "").lstrip("+")
    if not raw:
        return None
    try:
        return int(float(raw))
    except Exception:
        return None


def to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    raw = str(v).strip().replace(",", "").lstrip("+")
    if not raw:
        return None
    try:
        return float(raw)
    except Exception:
        return None


def first_present(row: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_symbol(code: Any) -> str:
    s = str(code or "").strip()
    if s.startswith("A") and len(s) > 1:
        return s[1:]
    return s


class KiwoomBrokerTruthClient:
    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        catalog: Optional[ApiCatalog] = None,
        executor: Any = None,
    ) -> None:
        self.s = settings or Settings.from_env()
        self.catalog = catalog or ApiCatalog.load(str(ensure_catalog_path()))
        self.executor = executor or get_executor(settings=self.s, catalog=self.catalog)

    def call(self, api_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        spec = self.catalog.get(api_id)
        req = PreparedRequest(
            api_id=api_id,
            method=spec.method or "POST",
            path=spec.path,
            headers={},
            query={},
            body=body,
        )
        result = self.executor.execute(req)
        payload = result.response.payload if result and result.response else {}
        return payload if isinstance(payload, dict) else {}
