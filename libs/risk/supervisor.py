from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

from libs.core.settings import Settings


@dataclass(frozen=True)
class AllowResult:
    allow: bool
    reason: str
    details: Dict[str, Any]


class Supervisor:
    """Risk guardrails (M7-1).

    This module must be deterministic and *must not* modify env or configs.
    It only enforces hard guardrails (env-driven) against action intents.

    Expected context keys (optional; can be extended):
      - daily_pnl_ratio: float  (e.g., -0.012 means -1.2% today)
      - per_trade_risk_ratio: float (expected max loss ratio for intended trade)
      - open_positions: int
      - last_order_epoch: int
      - now_epoch: int
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or Settings.from_env()

    def allow(self, intent: str, context: Dict[str, Any]) -> AllowResult:
        intent = (intent or "").lower().strip()
        now = int(context.get("now_epoch") or time.time())

        # --- Daily loss limit ---
        daily_pnl = float(context.get("daily_pnl_ratio", 0.0))
        if daily_pnl <= -float(self.s_value("RISK_DAILY_LOSS_LIMIT", 0.0)):
            return AllowResult(
                allow=False,
                reason="Daily loss limit exceeded",
                details={"daily_pnl_ratio": daily_pnl, "limit": float(self.s_value("RISK_DAILY_LOSS_LIMIT", 0.0))},
            )

        # --- Max positions ---
        open_pos = int(context.get("open_positions", 0))
        max_pos = int(self.s_value("RISK_MAX_POSITIONS", 1))
        if open_pos >= max_pos and intent in ("buy", "open", "enter"):
            return AllowResult(
                allow=False,
                reason="Max positions reached",
                details={"open_positions": open_pos, "max_positions": max_pos},
            )

        # --- Per-trade risk limit (expected worst-case loss ratio for intended trade) ---
        per_trade_risk = float(context.get("per_trade_risk_ratio", 0.0))
        per_trade_limit = float(self.s_value("RISK_PER_TRADE_LOSS_LIMIT", 0.0))
        if per_trade_limit > 0 and per_trade_risk > per_trade_limit:
            return AllowResult(
                allow=False,
                reason="Per-trade risk limit exceeded",
                details={"per_trade_risk_ratio": per_trade_risk, "limit": per_trade_limit},
            )

        # --- Cooldown ---
        cooldown = int(self.s_value("RISK_ORDER_COOLDOWN_SEC", 0))
        last_order = int(context.get("last_order_epoch", 0))
        if cooldown > 0 and last_order > 0 and (now - last_order) < cooldown:
            return AllowResult(
                allow=False,
                reason="Order cooldown active",
                details={"cooldown_sec": cooldown, "elapsed_sec": now - last_order},
            )

        return AllowResult(allow=True, reason="Allowed", details={"intent": intent})

    def s_value(self, key: str, default: Any) -> Any:
        # Settings reads env already; access via os.getenv would be ok but keep centralized.
        # Here we just use the Settings object defaults by mapping known keys.
        mapping = {
            "RISK_DAILY_LOSS_LIMIT": getattr(self.s, "risk_daily_loss_limit", None),
            "RISK_PER_TRADE_LOSS_LIMIT": getattr(self.s, "risk_per_trade_loss_limit", None),
            "RISK_MAX_POSITIONS": getattr(self.s, "risk_max_positions", None),
            "RISK_ORDER_COOLDOWN_SEC": getattr(self.s, "risk_order_cooldown_sec", None),
        }
        v = mapping.get(key, None)
        return default if v is None else v
