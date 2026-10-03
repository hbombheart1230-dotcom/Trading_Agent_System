from collections import defaultdict

from .contract import VERSION
from .outcomes import metrics


def aggregate(days):
    buckets = defaultdict(list)
    for day in days:
        for method, record in day.get('records', {}).items():
            feature = record['features']
            labels = {'surge': feature['btc_daily_context']['market_state'],
                      'session_gap': feature.get('crypto_time_alignment', {}).get('gap_type', 'UNKNOWN'),
                      'breakout': feature['btc_daily_context']['breakout_state'],
                      'reaction': feature['woori_opening']['reaction'],
                      'crypto_equity': feature['crypto_equity_confirm'],
                      'surge_x_equity': feature['btc_daily_context']['market_state'] + '|' + feature['crypto_equity_confirm'],
                      'local': feature['entry_methods'][method]['confirmation'],
                      'shadow_label': record['B']['label']}
            for horizon in ('09:30', '10:00', 'EOD'):
                outcome = (day['outcomes'].get(method) or {}).get(horizon) or {}
                for arm in ('A', 'B'):
                    selected = record['A'].get('eligible') if arm == 'A' else record['B']['label'] == 'FAST_BUY_CANDIDATE' or (method == 'PULLBACK' and record['B']['label'] == 'WAIT_PULLBACK_CANDIDATE')
                    if selected:
                        buckets[(record['phase'], 'arm', arm, method, horizon)].append(outcome)
                # Matched opportunity control is separate from actual A-selected performance.
                buckets[(record['phase'], 'opportunity', 'ALL', method, horizon)].append(outcome)
                for axis, value in labels.items():
                    buckets[(record['phase'], axis, value, method, horizon)].append(outcome)
    return [{'phase': p, 'axis': a, 'value': v, 'method': m, 'horizon': h, 'metrics': metrics(rows, len(rows))}
            for (p, a, v, m, h), rows in sorted(buckets.items())]


def render(payload):
    lines = ['# Q12 vNext Forward Validation', '', f"- Version: `{VERSION}`",
             f"- Through: {payload['day']}", f"- Evidence: {payload['evidence_status']}",
             '- Shadow only. A = existing Q12 candidate eligibility, not approval/fill.',
             '- No trade days and missing values are not losses. Entry methods are correlated, not independent signals.',
             '', '| Phase | Axis | Value | Entry | Exit | Signals | Evaluable | Missing | Win | Avg net % | Median % | PF | MFE % | MAE % | Review |',
             '|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for row in payload['summary']:
        m = row['metrics']
        vals = [row[k] for k in ('phase', 'axis', 'value', 'method', 'horizon')]
        vals += [m.get(k) for k in ('signal_count', 'evaluable_count', 'missing_evidence_count', 'win_rate', 'avg_return_pct', 'median_return_pct', 'profit_factor', 'avg_mfe_pct', 'avg_mae_pct', 'review_state')]
        lines.append('| ' + ' | '.join('-' if v is None else f'{v:.4f}' if isinstance(v, float) else str(v).replace('|', '/') for v in vals) + ' |')
    lines += ['', '## Daily Evidence', '', '```json', __import__('json').dumps(payload.get('current_features', {}), ensure_ascii=False, indent=2), '```',
              '', '- Company-specific event veto evidence: UNKNOWN unless a validated structured event is supplied.',
              '- 120-day available high is not an all-time high. No promotion is automatic.']
    return '\n'.join(lines) + '\n'
