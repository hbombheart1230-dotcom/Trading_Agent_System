from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .contract import KST, RULES, START_DAY, VERSION, PREVIOUS_VERSION, epoch
from .equities import fetch_equities
from .features import build_features, classify
from .outcomes import forward
from .report import aggregate, render
from .storage import digest, publish, read
from .time_alignment import fetch_alignment, session_context


def build_vnext(*, day, reports_root, signals, candles, control_payload, cost_pct, slippage_pct,
                allow_fetch=False, now=None, equity_loader=None, alignment_loader=None):
    now = now or datetime.now(KST)
    if day != now.astimezone(KST).date().isoformat() or day < START_DAY:
        return {'status': 'SKIPPED', 'reason': 'forward_only_no_historical_rebuild'}
    t = int(now.timestamp())
    root = Path(reports_root) / 'evaluation/baseline_btc_woori_tech/vnext' / VERSION
    folder = root / day
    context_path = folder / 'preopen_context.json'
    if context_path.exists():
        context = read(context_path)  # Corruption must never authorize replacement.
        if context.get('day') != day or context.get('version') != VERSION:
            raise ValueError('vnext_context_schema_mismatch')
    elif t <= epoch(day, '08:59') + 59 and allow_fetch:
        try:
            equities = (equity_loader or fetch_equities)(day)
        except Exception as exc:
            equities = {'status': 'UNKNOWN', 'reason': type(exc).__name__}
        try:
            aligned = (alignment_loader or fetch_alignment)(day, equities) if equity_loader is None or alignment_loader else signals.get('crypto_time_alignment', {})
        except Exception as exc:
            aligned = {'status': 'UNKNOWN', 'reason': type(exc).__name__}
        daily = deepcopy(signals.get('research_context') or {})
        # Reuse only bounded lookback inputs already supplied by Q12; no history backtest.
        daily['btc_usd_daily'] = list(daily.get('btc_usd_daily') or [])[-130:]
        daily['woori_daily'] = list(daily.get('woori_daily') or [])[-10:]
        context = publish(context_path, {'day': day, 'version': VERSION, 'observed_at': now.isoformat(),
            'equities': equities, 'daily_context': daily, 'crypto_time_alignment': aligned}, immutable=True)
    else:
        context = {'equities': {}, 'daily_context': {}, 'reason': 'preopen_context_missing_no_backfill'}
        prior = root.parent / PREVIOUS_VERSION / day / 'preopen_context.json'
        if prior.exists():
            old = read(prior)
            observed = datetime.fromisoformat(old['observed_at'])
            if old.get('day') == day and int(observed.timestamp()) <= epoch(day, '08:59') + 59:
                # Carry factual preopen inputs only. Never invent aligned prices after entry.
                try:
                    timing = session_context(day)
                except Exception:
                    timing = {}
                context = publish(context_path, {**old, 'version': VERSION, 'carried_from': str(prior),
                    'crypto_time_alignment': {**timing, 'status': 'UNKNOWN', 'reason': 'V1_did_not_capture_matched_BTC_interval'}}, immutable=True)
    signal_copy = deepcopy(signals)
    signal_copy['research_context'] = context['daily_context']
    signal_copy['crypto_time_alignment'] = context.get('crypto_time_alignment') or {}
    features, rows = build_features(day, signal_copy, candles, context['equities'], t)
    records = {}
    for method, entry in features['entry_methods'].items():
        path = folder / 'observations' / (method.replace(':', '') + '.json')
        if path.exists():
            records[method] = read(path)
        elif entry.get('status') == 'OBSERVED' and t >= int(entry.get('entry_epoch') or 0):
            # Pure existing candidate function; no dispatcher/commander/executor invoked.
            from libs.runtime.controlled_mock_lanes.signals import build_q12_candidate
            at = int(entry['entry_epoch'])
            at_features, _ = build_features(day, signal_copy, candles, context['equities'], at)
            a = build_q12_candidate(deepcopy(control_payload), now_epoch=at)
            a = a if a and (a.get('evidence') or {}).get('entry_method') == method else None
            record = {'version': VERSION, 'day': day, 'method': method, 'observed_at': now.isoformat(),
                'decision_epoch': at, 'phase': 'PROSPECTIVE' if t <= at + 300 else 'LATE_RECONSTRUCTION',
                'behavior_effect': 'shadow_only', 'order_execution_allowed': False,
                'definitions': RULES, 'rule_hash': digest(RULES),
                'control_source_hash': digest(control_payload),
                'A': {'eligible': bool(a), 'candidate': a, 'scope': 'existing_candidate_policy_not_fill'},
                'B': classify(at_features, method), 'features': at_features,
                'cost_model': {'cost_pct': cost_pct, 'slippage_pct': slippage_pct}}
            records[method] = publish(path, record, immutable=True)
    outcomes = {method: forward(day, record['features']['entry_methods'][method], rows,
                    record['cost_model']['cost_pct'] + record['cost_model']['slippage_pct'], t)
                for method, record in records.items()}
    for method, horizons in outcomes.items():
        for horizon, value in list(horizons.items()):
            path = folder / 'forward' / f"{method.replace(':', '')}_{horizon.replace(':', '')}.json"
            complete_path = path.with_name(path.stem + '_complete.json')
            if path.exists():
                horizons[horizon] = read(path)
            elif value.get('status') == 'OBSERVED':
                horizons[horizon] = publish(path, value, immutable=True)
            if complete_path.exists():
                horizons[horizon] = read(complete_path)
            elif value.get('path_status') == 'COMPLETE':
                first = horizons[horizon]
                if first.get('exit_price') == value.get('exit_price'):
                    horizons[horizon] = publish(complete_path, value, immutable=True)
    daily = {'version': VERSION, 'day': day, 'records': records, 'outcomes': outcomes}
    publish(folder / 'validation.json', daily)
    days = [read(p) for p in sorted(root.glob('*/validation.json')) if p.parent.name <= day]
    report = {**daily, 'current_features': features, 'summary': aggregate(days),
              'evidence_status': 'AVAILABLE' if any(v.get('status') == 'OBSERVED' for h in outcomes.values() for v in h.values()) else 'INSUFFICIENT_EVIDENCE'}
    publish(folder / 'comparison.json', report)
    (folder / 'daily_report.md').write_text(render(report), encoding='utf-8')
    return {'status': report['evidence_status'], 'observation_path': str(folder / 'observations'),
            'validation_path': str(folder / 'validation.json'), 'report_path': str(folder / 'daily_report.md')}
