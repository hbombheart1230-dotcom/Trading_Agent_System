from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class DefaultRuleEngine:
    """Injects sensible defaults so YAML stays minimal.

    Priority (low -> high):
      1) hardcoded safe defaults
      2) generated prefix defaults (data/specs/default_rules.json)
      3) generated api overrides   (data/specs/default_rules.json)
      4) caller ctx (explicit args or YAML mapping)

    Note: This engine should never require agents to know low-level params.
    """

    def __init__(self, rules_path: str = "data/specs/default_rules.json"):
        self.rules_path = Path(rules_path)
        self._loaded = False
        self.prefix_defaults: Dict[str, Dict[str, Any]] = {}
        self.api_overrides: Dict[str, Dict[str, Any]] = {}

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.rules_path.exists():
            return
        try:
            data = json.loads(self.rules_path.read_text(encoding="utf-8"))
            self.prefix_defaults = data.get("prefix_defaults") or {}
            self.api_overrides = data.get("api_overrides") or {}
        except Exception:
            # if broken, keep empty
            self.prefix_defaults = {}
            self.api_overrides = {}

    def apply(self, api_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        self._load()
        api_id = (api_id or "").strip()

        # 1) hardcoded safe defaults
        ctx.setdefault("dmst_stex_tp", "KRX")

        # 2) generated prefix defaults
        for pref, d in (self.prefix_defaults or {}).items():
            if api_id.startswith(pref):
                for k, v in (d or {}).items():
                    ctx.setdefault(k, v)

        # 3) generated api overrides
        d = (self.api_overrides or {}).get(api_id) or {}
        for k, v in d.items():
            ctx.setdefault(k, v)

        # 4) tiny hard constraints / normalization
        if api_id in ("kt10000", "kt10001"):
            if str(ctx.get("trde_tp")) == "3":
                ctx["ord_uv"] = ""  # market order

        if api_id == "ka10003":
            # ensure stk_cd exists (some specs omit body schema)
            if "stk_cd" not in ctx and "symbol" in ctx:
                ctx["stk_cd"] = ctx["symbol"]

        return ctx
