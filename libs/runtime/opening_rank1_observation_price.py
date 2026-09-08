"""Price provenance for Rank-1 observations; never fetch or invent prices."""
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo

from libs.runtime.runtime_output_helpers import to_epoch


def resolve_observation_price(*, selected, quote, rows, now_epoch):
    def positive(value):
        try:
            number = float(value)
            return number if isfinite(number) and number > 0 else None
        except (TypeError, ValueError):
            return None

    price = positive(selected.get("price"))
    if price:
        return {"observed_price": price, "price_source": selected.get("_monitor_price_source") or "selected.price"}
    stamp = to_epoch(quote.get("_observed_epoch") or quote.get("_observed_at_utc"))
    price = positive(quote.get("cur") or quote.get("price") or quote.get("current_price"))
    if price and stamp is not None and 0 <= now_epoch - stamp <= 90:
        return {"observed_price": price, "price_source": "market.quote"}
    candidates = []
    for row in rows:
        value = row.get("ts") or row.get("timestamp") or row.get("datetime")
        text = str(value or "")
        if text.isdigit() and len(text) in (12, 14):
            try:
                stamp = int(datetime.strptime(text, "%Y%m%d%H%M%S" if len(text) == 14 else "%Y%m%d%H%M").replace(tzinfo=ZoneInfo("Asia/Seoul")).timestamp())
            except ValueError:
                stamp = None
        else:
            stamp = to_epoch(value)
        price = positive(row.get("close"))
        if price and stamp is not None and 0 <= now_epoch - stamp <= 120:
            candidates.append((stamp, price))
    if candidates:
        return {"observed_price": max(candidates)[1], "price_source": "state.minute_ohlcv_by_symbol.close"}
    return {"observed_price": None, "price_source": "unavailable"}
