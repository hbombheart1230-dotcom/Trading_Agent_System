from copy import deepcopy
from ..hypothesis_features import build_hypothesis_features
from .contract import epoch, number, pct
from .equities import confirmation
from .time_alignment import project_alignment


def build_features(day, signals, candles, equities, now_epoch):
    # Reuse existing calculations on a sanitized, point-in-time single-day view.
    start, end = epoch(day, '09:00'), epoch(day, '15:30')
    counts = {}
    for r in candles:
        t = int(r.get('ts') or 0)
        counts[t] = counts.get(t, 0) + 1
    rows = sorted((dict(r) for r in candles if start <= int(r.get('ts') or 0) <= min(now_epoch, end)
                   and counts[int(r.get('ts') or 0)] == 1
                   and all((number(r.get(k)) or 0) > 0 for k in ('open', 'close', 'high', 'low'))), key=lambda r: r['ts'])
    payload = deepcopy(signals)
    if payload.get('btc_0855_capture_status') != 'CAPTURED':
        payload['btc_0855_capture_status'] = 'MISSING'
    features = build_hypothesis_features(day=day, candles=rows, btc_signals=payload)
    btc = features['btc_0855']
    target = epoch(day, '08:55')
    source_rows = (payload.get('btc_0855_captured_sources') or {}).get('btc_usd') or []
    source = next((r for r in reversed(source_rows) if 0 <= target - int(r.get('ts') or 0) <= 300), {})
    btc['price_usd'] = number(source.get('price'))
    for minutes in (5, 15, 60):
        btc[f'return_{minutes}m_pct'] = number(source.get(f'momentum_{minutes}m_pct'))
    daily = sorted((r for r in (payload.get('research_context') or {}).get('btc_usd_daily', [])
                    if 0 < int(r.get('ts') or 0) <= target - 86400), key=lambda r: r['ts'])
    # Daily context uses fixed UTC completed bars; rolling 3d/7d values are labeled accordingly.
    for days in (3, 7):
        basis = number(daily[-days]['close']) if len(daily) >= days else None
        btc[f'return_from_{days}d_closed_basis_pct'] = pct(btc['price_usd'], basis)
    context = features['btc_daily_context']
    context['market_state'] = ('EXTENDED' if context.get('prior_7d_strong_up_day_count', 0) > 0
                               else context.get('surge_state')) if context.get('status') == 'OBSERVED' else 'UNKNOWN'
    breaks = []
    for days in (20, 60, 120):
        window = daily[-days:]
        contiguous = len(window) == days and all(int(b['ts']) - int(a['ts']) == 86400 for a, b in zip(window, window[1:]))
        highs = [number(r.get('high')) for r in window]
        high = max(highs) if contiguous and all(h is not None and h > 0 for h in highs) else None
        context[f'distance_{days}d_high_pct'] = pct(btc['price_usd'], high)
        if high and btc['price_usd'] and btc['price_usd'] > high:
            breaks.append(f'{days}D_HIGH_BREAKOUT')
    context['breakout_state'] = breaks[-1] if breaks else ('NONE' if context.get('distance_20d_high_pct') is not None else 'UNKNOWN')
    context['breakout_ath'] = None
    context['ath_equivalent'] = '120D_AVAILABLE_HIGH_ONLY'
    context['important_price_breakout'] = 'UNKNOWN'
    context.pop('breakout_20d', None)
    context.pop('breakout_60d', None)
    features['crypto_equities'] = equities
    aligned = project_alignment(payload.get('crypto_time_alignment'), btc['price_usd'])
    features['crypto_time_alignment'] = aligned
    features['crypto_equity_confirm'] = confirmation(equities, aligned.get('btc_equity_interval_return_pct')
                                                     if aligned.get('status') == 'AVAILABLE' else None)
    features['legacy_unaligned_direction'] = confirmation(equities, btc.get('return_24h_pct'))
    gap, ret = features['woori_opening'].get('opening_gap_pct'), btc.get('return_24h_pct')
    reaction = 'UNKNOWN'
    if gap is not None and ret is not None and ret > 0:
        reaction = 'DIVERGENCE' if gap < 0 else 'OVERREACTION' if gap >= 10 else 'UNDERREACTION' if gap < 3 else 'FAIR_REACTION'
    features['woori_opening']['reaction'] = reaction
    for method, entry in features['entry_methods'].items():
        t = int(entry.get('entry_epoch') or 0)
        original = next((r for r in rows if r['ts'] == t), None)
        if original is None or (method == 'PULLBACK' and t != int(entry.get('trigger_epoch') or 0) + 60):
            entry.update(status='MISSING', entry_price=None, local_confirmation=None)
        elif method != 'PULLBACK' and t > start:
            required = list(range(start, t, 60))
            if not all(any(r['ts'] == stamp for r in rows) for stamp in required):
                entry.update(local_confirmation=None, reason='incomplete_confirmation_minutes')
        if original:
            entry['entry_price'] = original['open']
        entry['confirmation'] = 'UNKNOWN' if entry.get('local_confirmation') is None else 'CONFIRMED' if entry['local_confirmation'] else 'NOT_CONFIRMED'
    features['woori_specific_event'] = {'status': 'UNKNOWN', 'reason': 'no_point_in_time_structured_event_contract'}
    event = payload.get('woori_specific_event') or {}
    if (event.get('symbol') == '041190' and isinstance(event.get('adverse'), bool)
            and 0 < int(event.get('observed_epoch') or 0) <= now_epoch
            and event.get('source') and event.get('event_id')):
        features['woori_specific_event'] = {**event, 'status': 'OBSERVED'}
    features['checkpoints'] = {}
    for clock in ('09:00', '09:03', '09:05', '09:10', '09:15', '09:30', '10:00', '15:30'):
        t = epoch(day, clock)
        row = next((r for r in rows if r['ts'] == t), None)
        if row and now_epoch >= t + 60:
            features['checkpoints'][clock] = {'status': 'OBSERVED', 'ts': t, 'price': row['close'], 'open': row['open'], 'volume': number(row.get('volume'))}
        else:
            features['checkpoints'][clock] = {'status': 'MISSING_EVIDENCE'}
    closed_rows = [r for r in rows if r['ts'] + 60 <= now_epoch]
    features['day_range'] = {'high': max((r['high'] for r in closed_rows), default=None),
                             'low': min((r['low'] for r in closed_rows), default=None),
                             'status': 'FINAL' if features['checkpoints']['15:30']['status'] == 'OBSERVED' else 'INTRADAY'}
    return features, rows


def classify(features, method):
    btc = features['btc_0855'].get('return_24h_pct')
    confirm = features['crypto_equity_confirm']
    daily = features['btc_daily_context']
    reaction = features['woori_opening']['reaction']
    local = features['entry_methods'][method].get('local_confirmation')
    event = features['woori_specific_event']
    if event.get('status') == 'OBSERVED' and event.get('adverse') is True:
        return {'label': 'NO_TRADE_CANDIDATE', 'evidence_status': 'AVAILABLE', 'reason': 'structured_company_adverse_evidence_shadow_only'}
    if btc is None or confirm == 'UNKNOWN' or reaction == 'UNKNOWN' or daily['market_state'] == 'UNKNOWN' or daily['breakout_state'] == 'UNKNOWN' or local is None:
        return {'label': 'NO_TRADE_CANDIDATE', 'evidence_status': 'INSUFFICIENT_EVIDENCE', 'reason': 'required_evidence_missing'}
    if reaction == 'DIVERGENCE':
        label = 'NO_TRADE_CANDIDATE'
    elif confirm in ('MIXED', 'DIVERGENCE') or not local:
        label = 'DOWNGRADED'
    elif btc >= 4 and daily['market_state'] == 'EXTENDED' and reaction == 'OVERREACTION':
        label = 'WAIT_PULLBACK_CANDIDATE'
    elif btc >= 4 and daily['market_state'] == 'FIRST_SURGE' and 'BREAKOUT' in daily['breakout_state'] and reaction != 'OVERREACTION':
        label = 'FAST_BUY_CANDIDATE'
    else:
        label = 'DOWNGRADED'
    return {'label': label, 'evidence_status': 'AVAILABLE', 'reason': 'frozen_shadow_rules'}
