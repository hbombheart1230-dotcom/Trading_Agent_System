from statistics import median

from ..hypothesis_forward import summarize_outcomes
from .contract import epoch, number, pct


def forward(day, entry, candles, drag_pct, now_epoch):
    t, price = int(entry.get('entry_epoch') or 0), number(entry.get('entry_price'))
    output = {}
    if entry.get('status') != 'OBSERVED' or not price or price <= 0:
        return output
    for horizon in ('09:30', '10:00', 'EOD'):
        target = epoch(day, '15:30' if horizon == 'EOD' else horizon)
        window = [r for r in candles if t <= r['ts'] < target]
        point = next((r for r in candles if r['ts'] == target), None)
        # Exact timestamp only; never manufacture checkpoint prices from nearby bars.
        if not point or target <= t or now_epoch < target + (60 if horizon == 'EOD' else 0):
            output[horizon] = {'status': 'MISSING_EVIDENCE'}
            continue
        exit_price = point['close'] if horizon == 'EOD' else point['open']
        if horizon == 'EOD':
            window.append(point)
        expected = (target - t) // 60 + (1 if horizon == 'EOD' else 0)
        complete = len(window) == expected
        gross = pct(exit_price, price)
        output[horizon] = {'status': 'OBSERVED', 'exit_price': exit_price,
            'gross_return_pct': gross, 'net_return_pct': gross - drag_pct,
            'mfe_pct': max(0, pct(max(r['high'] for r in window), price)) if complete else None,
            'mae_pct': min(0, pct(min(r['low'] for r in window), price)) if complete else None,
            'path_status': 'COMPLETE' if complete else 'MISSING_EVIDENCE', 'entry_price': price}
    return output


def metrics(rows, signal_count):
    usable = [r for r in rows if r.get('status') == 'OBSERVED']
    result = summarize_outcomes(usable)
    if not usable:
        result.update(win_rate=None, avg_return_pct=None, profit_factor=None, max_drawdown_pct=None)
    result.update(signal_count=signal_count, evaluable_count=len(usable),
                  missing_evidence_count=signal_count-len(usable),
                  median_return_pct=median(r['net_return_pct'] for r in usable) if usable else None,
                  review_state='ANECDOTAL_ONLY' if len(usable) < 10 else 'PRELIMINARY' if len(usable) < 20
                  else 'INSUFFICIENT_FOR_PROMOTION' if len(usable) < 30 else 'REVIEW_ELIGIBLE_NOT_STATISTICAL_PROOF')
    return result
