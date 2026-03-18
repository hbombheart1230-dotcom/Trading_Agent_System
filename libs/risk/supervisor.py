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

    @staticmethod
    def _policy_position_sizing(context: Dict[str, Any]) -> Dict[str, Any]:
        policy = context.get("strategy_policy")
        if not isinstance(policy, dict):
            return {}
        entry_policy = policy.get("entry_policy")
        if not isinstance(entry_policy, dict):
            return {}
        sizing = entry_policy.get("position_sizing")
        if not isinstance(sizing, dict):
            return {}
        return dict(sizing)

    @staticmethod
    def _entry_order_qty(context: Dict[str, Any]) -> int:
        order = context.get("order")
        if not isinstance(order, dict):
            return 0
        try:
            return int(float(order.get("qty") or 0))
        except Exception:
            return 0

    def allow(self, intent: str, context: Dict[str, Any]) -> AllowResult:
        intent = (intent or "").lower().strip()
        now = int(context.get("now_epoch") or time.time())
        is_entry_intent = intent in ("buy", "open", "enter")

        # --- Daily loss limit ---
        daily_pnl = float(context.get("daily_pnl_ratio", 0.0))
        daily_limit = float(self.s_value("RISK_DAILY_LOSS_LIMIT", 0.0))
        if is_entry_intent and daily_limit > 0 and daily_pnl <= -daily_limit:
            return AllowResult(
                allow=False,
                reason="Daily loss limit exceeded",
                details={"daily_pnl_ratio": daily_pnl, "limit": daily_limit},
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
        if is_entry_intent and per_trade_limit > 0 and per_trade_risk > per_trade_limit:
            return AllowResult(
                allow=False,
                reason="Per-trade risk limit exceeded",
                details={"per_trade_risk_ratio": per_trade_risk, "limit": per_trade_limit},
            )

        # --- Cooldown ---
        cooldown = int(self.s_value("RISK_ORDER_COOLDOWN_SEC", 0))
        last_order = int(context.get("last_order_epoch", 0))
        if is_entry_intent and cooldown > 0 and last_order > 0 and (now - last_order) < cooldown:
            return AllowResult(
                allow=False,
                reason="Order cooldown active",
                details={"cooldown_sec": cooldown, "elapsed_sec": now - last_order},
            )

        # --- Strategy policy sizing rails ---
        if is_entry_intent:
            sizing = self._policy_position_sizing(context)
            qty = self._entry_order_qty(context)
            if sizing:
                max_qty = int(sizing.get("max_position_qty") or 0)
                min_qty = int(sizing.get("min_position_qty") or 0)
                lot_size = int(sizing.get("lot_size") or 0)

                if max_qty > 0 and qty > max_qty:
                    return AllowResult(
                        allow=False,
                        reason="Strategy policy max position qty exceeded",
                        details={
                            "order_qty": qty,
                            "max_position_qty": max_qty,
                            "policy_guard": "max_position_qty",
                        },
                    )

                if min_qty > 0 and qty > 0 and qty < min_qty:
                    return AllowResult(
                        allow=False,
                        reason="Strategy policy minimum position qty not met",
                        details={
                            "order_qty": qty,
                            "min_position_qty": min_qty,
                            "policy_guard": "min_position_qty",
                        },
                    )

                if lot_size > 1 and qty > 0 and (qty % lot_size) != 0:
                    return AllowResult(
                        allow=False,
                        reason="Strategy policy lot size violated",
                        details={
                            "order_qty": qty,
                            "lot_size": lot_size,
                            "policy_guard": "lot_size",
                        },
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
