"""Align crypto returns to the equity interval; weekend moves are separate."""
from datetime import date, datetime, timedelta
from functools import lru_cache

from .contract import KST, epoch, number, pct


@lru_cache(maxsize=32)
def session_context(day):
    import exchange_calendars as xcals
    calendar = xcals.get_calendar('XNYS')
    requested = date.fromisoformat(day) - timedelta(days=1)
    while requested.weekday() > 4:
        requested -= timedelta(days=1)
    # A holiday is not silently replaced with an older weekday observation.
    if not calendar.is_session(requested.isoformat()):
        return {'status': 'UNKNOWN', 'reason': 'US_MARKET_HOLIDAY', 'expected_session': requested.isoformat()}
    previous = calendar.previous_session(requested.isoformat())
    end = calendar.session_close(requested.isoformat())
    start = calendar.session_close(previous)
    target = epoch(day, '08:55')
    age_hours = (target - int(end.timestamp())) / 3600
    return {'status': 'AVAILABLE', 'session': requested.isoformat(), 'previous_session': str(previous.date()),
            'us_previous_close_epoch': int(start.timestamp()), 'us_close_epoch': int(end.timestamp()),
            'us_close_kst': end.to_pydatetime().astimezone(KST).isoformat(), 'age_hours': age_hours,
            'gap_type': 'WEEKEND' if datetime.fromisoformat(day).weekday() == 0 else 'EXTENDED_CLOSURE' if age_hours > 30 else 'OVERNIGHT',
            'calendar': 'exchange_calendars:XNYS:4.13.2'}


def capture_alignment(day, equities, rows):
    try:
        context = dict(session_context(day))
    except Exception as exc:
        return {'status': 'UNKNOWN', 'reason': f'calendar_unavailable:{type(exc).__name__}'}
    if context['status'] != 'AVAILABLE':
        return context
    if any((equities.get(t) or {}).get('session') != context['session'] or
           (equities.get(t) or {}).get('previous_session') != context['previous_session'] for t in ('COIN', 'MSTR')):
        return {**context, 'status': 'UNKNOWN', 'reason': 'equity_interval_missing_or_mismatch'}
    points = {}
    for name in ('us_previous_close_epoch', 'us_close_epoch'):
        # 5-minute OPEN at the exact boundary, never its future five-minute CLOSE.
        matched = [r for r in rows if int(r.get('ts') or 0) == context[name]]
        value = number(matched[0].get('open')) if len(matched) == 1 else None
        points[name.replace('_epoch', '_btc_price')] = value if value and value > 0 else None
    same = pct(points['us_close_btc_price'], points['us_previous_close_btc_price'])
    return {**context, **points, 'status': 'AVAILABLE' if same is not None else 'UNKNOWN',
            'reason': '' if same is not None else 'exact_US_close_BTC_reference_missing',
            'btc_equity_interval_return_pct': same, 'source': 'yfinance:BTC-USD:5m:exact_boundary_open'}


def fetch_alignment(day, equities):
    import yfinance as yf
    frame = yf.Ticker('BTC-USD').history(period='5d', interval='5m', auto_adjust=False, timeout=8)
    # Do not reuse the legacy provider's missing-OPEN -> CLOSE fallback here.
    rows = [{'ts': int(index.timestamp()), 'open': number(row.get('Open'))}
            for index, row in frame.iterrows()]
    return capture_alignment(day, equities, rows)


def project_alignment(context, btc_price):
    alignment = dict(context or {})
    alignment['btc_since_us_close_pct'] = pct(number(btc_price), number(alignment.get('us_close_btc_price')))
    return alignment
