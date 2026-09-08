"""Bounded, optional US close context. No BTC-primary provider changes."""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from .contract import number, pct

NY = ZoneInfo('America/New_York')


def expected_session(day):
    session = date.fromisoformat(day) - timedelta(days=1)
    while session.weekday() > 4:
        session -= timedelta(days=1)
    return session.isoformat()


def session_return(rows, day):
    expected = expected_session(day)
    valid = sorted((r for r in rows if r.get('session', '') <= expected
                    and (number(r.get('close')) or 0) > 0), key=lambda r: r['session'])
    if len(valid) < 2 or valid[-1]['session'] != expected:
        return {'status': 'UNKNOWN', 'reason': 'holiday_or_missing_expected_session', 'expected_session': expected}
    if valid[-2]['session'] == expected or (date.fromisoformat(expected) - date.fromisoformat(valid[-2]['session'])).days > 4:
        return {'status': 'UNKNOWN', 'reason': 'invalid_previous_session', 'expected_session': expected}
    return {'status': 'OBSERVED', 'session': expected, 'previous_session': valid[-2]['session'],
            'close': valid[-1]['close'], 'previous_close': valid[-2]['close'],
            'return_pct': pct(valid[-1]['close'], valid[-2]['close']),
            'definition': 'regular-session close-to-close, split-adjusted by provider; auto_adjust=False'}


def fetch_equities(day):
    import yfinance as yf
    result = {}
    for ticker in ('COIN', 'MSTR'):
        try:
            frame = yf.Ticker(ticker).history(period='1mo', interval='1d', auto_adjust=False, prepost=False, timeout=8)
            rows = [{'session': idx.to_pydatetime().astimezone(NY).date().isoformat(), 'close': number(row['Close'])}
                    for idx, row in frame.iterrows()]
            result[ticker] = {**session_return(rows, day), 'source': f'yfinance:{ticker}:1d'}
        except Exception as exc:
            result[ticker] = {'status': 'UNKNOWN', 'reason': type(exc).__name__}
    return result


def confirmation(equities, btc_return):
    values = [number((equities.get(t) or {}).get('return_pct'))
              if (equities.get(t) or {}).get('status') == 'OBSERVED' else None for t in ('COIN', 'MSTR')]
    if btc_return is None or btc_return == 0 or any(v is None for v in values):
        return 'UNKNOWN'
    aligned = [v * btc_return > 0 for v in values]
    if all(aligned):
        return 'STRONG' if all(abs(v) >= 5 for v in values) else 'CONFIRM'
    if all(v * btc_return < 0 for v in values):
        return 'DIVERGENCE'
    return 'MIXED'
