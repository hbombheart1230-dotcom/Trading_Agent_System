from __future__ import annotations

# Thin compatibility facade for Phase 5-2:
# keep the existing operator_ui import path stable while moving
# read-only trade payload loading into libs.reporting.

from libs.reporting.trade_read_model import load_trade_report_payloads

__all__ = ["load_trade_report_payloads"]
