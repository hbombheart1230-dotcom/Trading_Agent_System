from datetime import datetime, timedelta, timezone
from math import isfinite

VERSION = 'Q12_CRYPTO_EQUITY_CONFIRM_V2_ALIGNED_SHADOW'
PREVIOUS_VERSION = 'Q12_CRYPTO_EQUITY_CONFIRM_V1_SHADOW'
START_DAY = '2026-09-07'
KST = timezone(timedelta(hours=9))
RULES = {
    'btc_strong_24h_pct': 4.0,
    'first_surge': 'BTC 24h >=3%; zero completed daily gains >=3% in preceding seven days',
    'extended': 'at least one completed daily gain >=3% in preceding seven days',
    'equity_strong_abs_pct': 5.0,
    'equity_direction_basis': 'BTC return between the SAME two US session closes; never latest BTC 24h return',
    'weekend': 'US Friday close age and BTC since US close separate from matched equity interval',
    'overreaction_gap_pct': 10.0,
    'underreaction_gap_pct': 3.0,
    'local_confirmation': 'prior completed minute volume ratio >=1.2 OR price above opening/prior high',
    'pullback': 'existing first 09:05-09:30 VWAP touch/reclaim then contiguous next minute OPEN',
    'breakout': 'price exceeds all valid closed daily highs in exact 20/60 day window; 120-day available high is NOT ATH',
    'us_session': 'last calendar weekday preceding Korean day; missing session (holiday or feed gap) => UNKNOWN, never older close substitution',
    'timing': '08:55 BTC immutable capture; equity context observed no later than 08:59:59 KST',
    'event': 'structured adverse flag with symbol 041190 and observed_at <= decision; otherwise UNKNOWN',
    'units': 'all return/cost fields percentage points, win_rate fraction',
}


def number(value):
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def epoch(day, clock):
    return int(datetime.fromisoformat(f'{day}T{clock}:00').replace(tzinfo=KST).timestamp())


def pct(price, basis):
    return (price / basis - 1) * 100 if price is not None and basis and basis > 0 else None
