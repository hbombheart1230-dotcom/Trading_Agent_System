from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from libs.catalog.api_catalog import ApiSpec


@dataclass(frozen=True)
class PreparedRequest:
    api_id: str
    method: str
    path: str
    headers: Dict[str, Any]
    query: Dict[str, Any]
    body: Dict[str, Any]


@dataclass(frozen=True)
class PrepareResult:
    action: str  # 'ready' or 'ask'
    request: Optional[PreparedRequest]
    missing: List[str]
    question: str
    reason: str


class ApiRequestBuilder:
    """Prepare-only module.
    Converts (ApiSpec + context) into a structured request object.
    No HTTP calls.
    """

    # Common aliases (extend later without breaking)
    ALIASES: Dict[str, List[str]] = {
        "account_no": ["account", "account_id", "acct_no", "accno"],
        "ticker": ["symbol", "code", "stock_code", "종목코드"],
        "qty": ["quantity", "amount", "수량"],
        "price": ["order_price", "단가", "가격"],
    }

    # Headers that are injected/managed by executors (token/app credentials/api-id)
    # These should NOT be required from the agent/context.
    MANAGED_HEADERS = {
        'authorization',
        'appkey',
        'appsecret',
        'api-id',
        'api_id',
    }

    def prepare(self, spec: ApiSpec, context: Dict[str, Any]) -> PrepareResult:
        schema = self._normalize_params_schema(spec.params or {})
        headers, query, body = {}, {}, {}
        missing: List[str] = []

        for name, meta in schema.items():
            loc = meta.get("in", "query")
            required = bool(meta.get("required", False))

            value, found = self._find_value(name, context)
            if not found:
                # Executor will inject auth/app headers automatically.
                if loc == "header" and name.lower() in self.MANAGED_HEADERS:
                    continue
                if required:
                    missing.append(name)
                continue

            if loc == "header":
                headers[name] = value
            elif loc == "path":
                # keep in query; actual path templating can be added later
                query[name] = value
            elif loc == "body":
                body[name] = value
            else:
                query[name] = value

        if missing:
            q = "다음 값이 필요해요: " + ", ".join(missing)
            return PrepareResult(
                action="ask",
                request=None,
                missing=missing,
                question=q,
                reason="Missing required parameters",
            )

        # --- Pass-through: if spec lacks body schema (or is incomplete),
        # include remaining context keys into body for POST/PUT/PATCH requests.
        method = (spec.method or '').upper()
        if method in ('POST','PUT','PATCH'):
            known = set(schema.keys())
            # Only add keys not already mapped to header/query/body
            for k, v in context.items():
                if k in known or k in headers or k in query or k in body:
                    continue
                if k.lower() in self.MANAGED_HEADERS:
                    continue
                # drop empty placeholders
                if v is None or v == '':
                    continue
                body[k] = v

        req = PreparedRequest(
            api_id=spec.api_id,
            method=spec.method or "",
            path=spec.path or "",
            headers=headers,
            query=query,
            body=body,
        )
        return PrepareResult(
            action="ready",
            request=req,
            missing=[],
            question="",
            reason="All required parameters resolved",
        )

    def _find_value(self, name: str, context: Dict[str, Any]) -> Tuple[Any, bool]:
        if name in context:
            return context[name], True
        for alias in self.ALIASES.get(name, []):
            if alias in context:
                return context[alias], True
        return None, False

    def _normalize_params_schema(self, params: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Support multiple possible schema shapes.
        Accepted shapes:
          1) { "field": {"in":"query","required":True} , ... }
          2) { "query": [{"name":"field","required":True}, ...], "body": [...] }
          3) { "fields": [ {"name":"field","in":"query","required":True}, ... ] }
        """
        schema: Dict[str, Dict[str, Any]] = {}

        # shape 1
        if all(isinstance(v, dict) for v in params.values()) and not any(k in params for k in ("query", "body", "fields")):
            for k, v in params.items():
                schema[k] = {"in": v.get("in", "query"), "required": bool(v.get("required", False))}
            return schema

        # shape 2
        for loc in ("query", "body", "header", "path"):
            if loc in params and isinstance(params[loc], list):
                for item in params[loc]:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if not name:
                        continue
                    schema[name] = {"in": loc, "required": bool(item.get("required", False))}
        if schema:
            return schema

        # shape 3
        if "fields" in params and isinstance(params["fields"], list):
            for item in params["fields"]:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not name:
                    continue
                schema[name] = {"in": item.get("in", "query"), "required": bool(item.get("required", False))}
            return schema

        return schema