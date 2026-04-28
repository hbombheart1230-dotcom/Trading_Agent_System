from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from libs.core.http_client import HttpClient
from libs.core.settings import Settings
from libs.core.symbols import normalize_symbol
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _read_nested(root: Any, *path: str) -> Any:
    cursor = root if isinstance(root, dict) else {}
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def _first_explicit(*values: Any) -> Any:
    for raw in values:
        if raw not in (None, ""):
            return raw
    return None


def _clean_text(v: Any) -> str:
    return str(v or "").strip()


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        text = str(v if v is not None else "").strip()
        if not text:
            return float(default)
        text = text.replace(",", "").replace("%", "")
        text = text.replace("--", "-")
        return float(text)
    except Exception:
        return float(default)


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(str(v if v is not None else "").replace(",", "").replace("--", "-").strip()))
    except Exception:
        return int(default)


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(float(lo), min(float(hi), float(v)))


def _round4(v: Any) -> float:
    return round(float(_to_float(v)), 4)


def _norm_symbol(v: Any) -> str:
    return normalize_symbol(v)


def _first(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _split_text_items(raw: Any) -> List[str]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str):
        values = re.split(r"[,;|\s]+", raw)
    else:
        values = []
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        text = _clean_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _symbols_from_any(raw: Any) -> List[str]:
    if isinstance(raw, dict):
        candidates = list(raw.values())
    elif isinstance(raw, list):
        candidates = raw
    elif isinstance(raw, str):
        candidates = _split_text_items(raw)
    else:
        candidates = []
    out: List[str] = []
    seen: set[str] = set()
    for item in candidates:
        if isinstance(item, dict):
            symbol = _norm_symbol(
                _first(item, "symbol", "stk_cd", "stkcode", "stk_code", "code", "isu_cd")
            )
        else:
            symbol = _norm_symbol(item)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    return out


def _extract_payload_rows(payload: Any, preferred_keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for key in preferred_keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return [dict(row) for row in value if isinstance(row, dict)]
    return []


def normalize_theme_group(row: Any) -> Dict[str, Any]:
    if isinstance(row, str):
        name = _clean_text(row)
        return {
            "theme_code": name.lower().replace(" ", "_"),
            "theme_name": name,
            "stock_count": 0,
            "rising_count": 0,
            "falling_count": 0,
            "change_rate": 0.0,
            "period_return": 0.0,
            "main_stocks": [],
            "raw": {"value": row},
        }
    if not isinstance(row, dict):
        return {}

    name = _clean_text(_first(row, "theme_name", "thema_nm", "name", "theme", "sector"))
    code = _clean_text(_first(row, "theme_code", "thema_grp_cd", "code", "group_code", "theme_id"))
    if not name and code:
        name = code
    if not code and name:
        code = name.lower().replace(" ", "_")
    if not name:
        return {}

    main_stocks = _symbols_from_any(_first(row, "main_stocks", "main_stk", "symbols", "components"))
    stock_count = _to_int(_first(row, "stock_count", "stk_num", "symbol_count"), len(main_stocks))
    return {
        "theme_code": code,
        "theme_name": name,
        "stock_count": int(max(0, stock_count)),
        "rising_count": int(max(0, _to_int(_first(row, "rising_count", "rising_stk_num", "up_count")))),
        "falling_count": int(max(0, _to_int(_first(row, "falling_count", "fall_stk_num", "down_count")))),
        "change_rate": _round4(_first(row, "change_rate", "flu_rt", "chg_rate", "change_pct")),
        "period_return": _round4(_first(row, "period_return", "dt_prft_rt", "return_rate")),
        "main_stocks": main_stocks,
        "raw": dict(row),
    }


def normalize_theme_component(row: Any) -> Dict[str, Any]:
    if isinstance(row, str):
        symbol = _norm_symbol(row)
        return {"symbol": symbol, "name": "", "change_rate": 0.0, "period_return": 0.0, "volume": 0.0, "raw": row} if symbol else {}
    if not isinstance(row, dict):
        return {}
    symbol = _norm_symbol(_first(row, "symbol", "stk_cd", "stkcode", "stk_code", "code", "isu_cd"))
    if not symbol:
        return {}
    return {
        "symbol": symbol,
        "name": _clean_text(_first(row, "name", "stk_nm", "stock_name", "isu_nm")),
        "change_rate": _round4(_first(row, "change_rate", "flu_rt", "chg_rate", "change_pct")),
        "period_return": _round4(_first(row, "period_return", "dt_prft_rt_n", "dt_prft_rt", "return_rate")),
        "volume": float(max(0.0, _to_float(_first(row, "volume", "acc_trde_qty", "trde_qty")))),
        "raw": dict(row),
    }


def _dedup_groups(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        name = _clean_text(row.get("theme_name"))
        key = (name or _clean_text(row.get("theme_code"))).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _dedup_components(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        symbol = _norm_symbol(row.get("symbol"))
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized = dict(row)
        normalized["symbol"] = symbol
        out.append(normalized)
    return out


def _state_mock_groups(state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    for key in ("mock_theme_groups", "kiwoom_theme_groups", "theme_groups"):
        raw = state.get(key)
        if isinstance(raw, list):
            rows = _dedup_groups([normalize_theme_group(row) for row in raw])
            rows = [row for row in rows if row]
            if rows:
                return rows, f"state.{key}"
    raw_env = os.getenv("MOCK_THEME_GROUPS", "")
    if raw_env.strip():
        rows = _dedup_groups([normalize_theme_group(name) for name in _split_text_items(raw_env)])
        rows = [row for row in rows if row]
        if rows:
            return rows, "env.MOCK_THEME_GROUPS"
    return [], ""


def _state_mock_component_map(state: Dict[str, Any]) -> Tuple[Dict[str, List[Dict[str, Any]]], str]:
    for key in ("mock_theme_component_map", "theme_component_map", "mock_theme_map"):
        raw = state.get(key)
        if isinstance(raw, dict):
            out: Dict[str, List[Dict[str, Any]]] = {}
            for name, values in raw.items():
                theme_key = _clean_text(name)
                if not theme_key:
                    continue
                if isinstance(values, list):
                    rows = [normalize_theme_component(row) for row in values]
                else:
                    rows = [normalize_theme_component(sym) for sym in _symbols_from_any(values)]
                rows = _dedup_components([row for row in rows if row])
                if rows:
                    out[theme_key] = rows
            if out:
                return out, f"state.{key}"

    raw_env = os.getenv("MOCK_THEME_COMPONENT_MAP", "").strip()
    if not raw_env:
        return {}, ""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in [x.strip() for x in raw_env.split(";") if x.strip()]:
        if ":" not in chunk:
            continue
        name, symbols = chunk.split(":", 1)
        rows = _dedup_components([normalize_theme_component(sym) for sym in _split_text_items(symbols)])
        rows = [row for row in rows if row]
        if rows:
            out[_clean_text(name)] = rows
    return out, "env.MOCK_THEME_COMPONENT_MAP" if out else ""


def _live_fetch_enabled(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    if os.getenv("PYTEST_CURRENT_TEST") and not _is_trueish(os.getenv("PYTEST_ALLOW_LIVE_KIWOOM_FETCH", "false")):
        return False
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    scanner_policy = policy.get("scanner") if isinstance(policy.get("scanner"), dict) else {}

    explicit_theme_raw = _first_explicit(
        state.get("kiwoom_theme_live_fetch"),
        state.get("theme_live_fetch"),
        policy.get("kiwoom_theme_live_fetch"),
        policy.get("theme_live_fetch"),
        os.getenv("KIWOOM_THEME_LIVE_FETCH"),
    )
    if explicit_theme_raw not in (None, ""):
        return _is_trueish(explicit_theme_raw)

    # Runtime ownership is Commander-first. Scanner live Kiwoom fetch implies
    # theme live fetch unless the theme-specific switch above explicitly opts out.
    scanner_live_raw = _first_explicit(
        _read_nested(applied_policy, "scanner", "kiwoom", "live_fetch"),
        _read_nested(scanner_policy, "kiwoom", "live_fetch"),
        policy.get("kiwoom_candidate_live_fetch"),
        policy.get("kiwoom_live_fetch"),
        state.get("kiwoom_candidate_live_fetch"),
    )
    if scanner_live_raw not in (None, ""):
        return _is_trueish(scanner_live_raw)
    return False


def _fetch_components_enabled(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    explicit_component_raw = _first_explicit(
        state.get("kiwoom_theme_fetch_components"),
        state.get("theme_fetch_components"),
        policy.get("kiwoom_theme_fetch_components"),
        policy.get("theme_fetch_components"),
        os.getenv("KIWOOM_THEME_FETCH_COMPONENTS"),
    )
    if explicit_component_raw not in (None, ""):
        return _is_trueish(explicit_component_raw)
    return _live_fetch_enabled(state, policy)


@dataclass(frozen=True)
class KiwoomThemeFetchResult:
    url: str
    status_code: int | None
    ok: bool
    payload: Dict[str, Any]


class KiwoomThemeReader:
    """Reader for Kiwoom theme endpoints.

    - ka90001: theme group ranking, endpoint /api/dostk/thme
    - ka90002: theme components, endpoint /api/dostk/thme

    Live calls are intentionally opt-in through Commander/policy/state flags.
    """

    ENDPOINT = "/api/dostk/thme"
    API_ID_THEME_GROUPS = "ka90001"
    API_ID_THEME_COMPONENTS = "ka90002"

    def __init__(self, settings: Settings, http: HttpClient, token: KiwoomTokenClient):
        self.s = settings
        self.http = http
        self.token = token

    @classmethod
    def from_env(cls) -> "KiwoomThemeReader":
        s = Settings.from_env()
        http = HttpClient(
            base_url=s.base_url,
            timeout_sec=int(s.kiwoom_http_timeout_sec),
            retry_max=int(s.kiwoom_retry_max),
        )
        token = KiwoomTokenClient(s, http)
        return cls(s, http, token)

    def _headers(self, api_id: str) -> Dict[str, Any]:
        tok = self.token.ensure_token(dry_run=False)
        if not tok.token:
            raise RuntimeError(f"Token not available: {tok.action} {tok.reason}")
        headers: Dict[str, Any] = {}
        headers.update(self.token.auth_headers(tok.token))
        headers["Content-Type"] = "application/json;charset=UTF-8"
        headers["api-id"] = str(api_id)
        if self.s.kiwoom_app_key:
            headers.setdefault("appkey", self.s.kiwoom_app_key)
        if self.s.kiwoom_app_secret:
            headers.setdefault("appsecret", self.s.kiwoom_app_secret)
        return headers

    def _post(self, *, api_id: str, body: Dict[str, Any]) -> KiwoomThemeFetchResult:
        url, resp = self.http.request(
            "POST",
            self.ENDPOINT,
            headers=self._headers(api_id),
            json_body=body,
            dry_run=False,
        )
        if resp is None:
            return KiwoomThemeFetchResult(url=url, status_code=None, ok=False, payload={})
        try:
            payload = json.loads(resp.text or "{}")
        except Exception:
            payload = {}
        return KiwoomThemeFetchResult(
            url=url,
            status_code=int(resp.status_code),
            ok=int(resp.status_code) < 400,
            payload=payload,
        )

    def get_theme_groups(self, *, limit: int = 20, date_tp: str = "10", stex_tp: str = "1") -> List[Dict[str, Any]]:
        result = self._post(
            api_id=self.API_ID_THEME_GROUPS,
            body={
                "qry_tp": "0",
                "stk_cd": "",
                "date_tp": str(date_tp or "10"),
                "thema_nm": "",
                "flu_pl_amt_tp": "1",
                "stex_tp": str(stex_tp or "1"),
            },
        )
        if not result.ok:
            return []
        rows = _extract_payload_rows(result.payload, ("thema_grp", "theme_group", "output", "data", "list"))
        normalized = [normalize_theme_group(row) for row in rows]
        normalized = _dedup_groups([row for row in normalized if row])
        return normalized[: max(1, int(limit))]

    def get_theme_components(
        self,
        *,
        theme_code: str,
        limit: int = 100,
        stex_tp: str = "1",
    ) -> List[Dict[str, Any]]:
        code = _clean_text(theme_code)
        if not code:
            return []
        result = self._post(
            api_id=self.API_ID_THEME_COMPONENTS,
            body={"thema_grp_cd": code, "stex_tp": str(stex_tp or "1")},
        )
        if not result.ok:
            return []
        rows = _extract_payload_rows(result.payload, ("thema_comp_stk", "theme_components", "output", "data", "list"))
        normalized = [normalize_theme_component(row) for row in rows]
        normalized = _dedup_components([row for row in normalized if row])
        return normalized[: max(1, int(limit))]


def _component_strength(rows: List[Dict[str, Any]]) -> float:
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        return 0.0
    change_scores = [_clamp(_to_float(row.get("change_rate")) / 10.0) for row in rows]
    period_scores = [_clamp(_to_float(row.get("period_return")) / 30.0) for row in rows]
    avg_change = sum(change_scores) / max(1, len(change_scores))
    avg_period = sum(period_scores) / max(1, len(period_scores))
    return float(_clamp((0.70 * avg_change) + (0.30 * avg_period)))


def _score_theme(group: Dict[str, Any], components: List[Dict[str, Any]]) -> Dict[str, float]:
    stock_count = max(1, _to_int(group.get("stock_count"), 0))
    rising = _to_int(group.get("rising_count"), 0)
    falling = _to_int(group.get("falling_count"), 0)
    breadth = _clamp(float(rising - falling) / float(stock_count))
    period_norm = _clamp(_to_float(group.get("period_return")) / 30.0)
    change_norm = _clamp(_to_float(group.get("change_rate")) / 10.0)
    component_norm = _component_strength(components)
    score = _clamp((0.35 * period_norm) + (0.25 * change_norm) + (0.25 * breadth) + (0.15 * component_norm))
    return {
        "score": round(float(score), 4),
        "period_return_component": round(float(period_norm), 4),
        "change_rate_component": round(float(change_norm), 4),
        "breadth_component": round(float(breadth), 4),
        "component_strength": round(float(component_norm), 4),
    }


def build_theme_strength_packet(
    state: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
    *,
    limit: int = 8,
    component_limit_per_theme: int = 12,
) -> Dict[str, Any]:
    runtime_state = state if isinstance(state, dict) else {}
    runtime_policy = policy if isinstance(policy, dict) else {}
    max_groups = max(1, int(limit))
    max_components = max(0, int(component_limit_per_theme))

    groups, group_source = _state_mock_groups(runtime_state)
    component_map, component_source = _state_mock_component_map(runtime_state)
    source = "state_mock" if group_source.startswith("state.") else ("env_mock" if group_source.startswith("env.") else "")
    status = "ok" if groups else ""
    reason = group_source or ""

    if not groups and _live_fetch_enabled(runtime_state, runtime_policy):
        try:
            reader = KiwoomThemeReader.from_env()
            date_tp = str(runtime_policy.get("kiwoom_theme_date_tp") or runtime_state.get("kiwoom_theme_date_tp") or "10")
            stex_tp = str(runtime_policy.get("kiwoom_theme_stex_tp") or runtime_state.get("kiwoom_theme_stex_tp") or "1")
            groups = reader.get_theme_groups(limit=max_groups, date_tp=date_tp, stex_tp=stex_tp)
            source = "kiwoom_live"
            status = "ok" if groups else "empty"
            reason = "ka90001"
            if groups and _fetch_components_enabled(runtime_state, runtime_policy):
                for group in groups[:max_groups]:
                    code = _clean_text(group.get("theme_code"))
                    name = _clean_text(group.get("theme_name"))
                    rows = reader.get_theme_components(theme_code=code, limit=max_components, stex_tp=stex_tp)
                    if rows:
                        component_map[name] = rows
                component_source = "kiwoom_live.ka90002" if component_map else component_source
        except Exception as e:
            groups = []
            source = "kiwoom_live"
            status = "unavailable"
            reason = f"{type(e).__name__}:{e}"

    if not groups:
        return {
            "schema_version": "kiwoom_theme_strength.v1",
            "source": source or "unavailable",
            "status": status or "unavailable",
            "reason": reason or "kiwoom_theme_live_fetch_disabled",
            "fallback_used": True,
            "groups": [],
            "top_themes": [],
            "theme_scores": {},
            "theme_map": {},
            "component_symbols_by_theme": {},
            "component_source": component_source,
            "formula": {
                "period_return": 0.35,
                "change_rate": 0.25,
                "breadth": 0.25,
                "component_strength": 0.15,
            },
        }

    groups = groups[:max_groups]
    component_symbols_by_theme: Dict[str, List[str]] = {}
    theme_map: Dict[str, List[str]] = {}
    top_rows: List[Dict[str, Any]] = []
    theme_scores: Dict[str, float] = {}

    for group in groups:
        name = _clean_text(group.get("theme_name"))
        code = _clean_text(group.get("theme_code"))
        candidates = []
        for key in (name, code, name.lower(), code.lower()):
            if key and key in component_map:
                candidates = list(component_map.get(key) or [])
                break
        if not candidates and group.get("main_stocks"):
            candidates = [normalize_theme_component(sym) for sym in list(group.get("main_stocks") or [])]
            candidates = [row for row in candidates if row]
        candidates = _dedup_components(candidates)[:max_components] if max_components > 0 else []
        symbols = [str(row.get("symbol") or "") for row in candidates if str(row.get("symbol") or "").strip()]
        score_parts = _score_theme(group, candidates)
        top_row = {
            "theme_code": code,
            "theme_name": name,
            "score": float(score_parts.get("score") or 0.0),
            "stock_count": int(group.get("stock_count") or 0),
            "rising_count": int(group.get("rising_count") or 0),
            "falling_count": int(group.get("falling_count") or 0),
            "change_rate": float(group.get("change_rate") or 0.0),
            "period_return": float(group.get("period_return") or 0.0),
            "score_components": score_parts,
            "component_count": int(len(symbols)),
        }
        top_rows.append(top_row)
        theme_scores[name] = float(top_row["score"])
        if symbols:
            component_symbols_by_theme[name] = symbols
            theme_map[name] = symbols

    top_rows.sort(key=lambda row: (-float(row.get("score") or 0.0), str(row.get("theme_name") or "")))
    theme_scores = {str(row.get("theme_name") or ""): float(row.get("score") or 0.0) for row in top_rows if row.get("theme_name")}
    return {
        "schema_version": "kiwoom_theme_strength.v1",
        "source": source or "state_mock",
        "status": status or "ok",
        "reason": reason or group_source or "theme_groups_available",
        "fallback_used": False,
        "groups": groups,
        "top_themes": top_rows,
        "theme_scores": theme_scores,
        "theme_map": theme_map,
        "component_symbols_by_theme": component_symbols_by_theme,
        "component_source": component_source,
        "formula": {
            "period_return": 0.35,
            "change_rate": 0.25,
            "breadth": 0.25,
            "component_strength": 0.15,
        },
    }
