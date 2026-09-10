"""Q12 decision inputs, independent of the expensive reporting projection."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .contracts import HYPOTHESIS_CONTRACT_ID
from .hypothesis_features import _btc_0855, build_hypothesis_features
from .point_in_time_capture import DEFAULT_ROOT, capture_paths, merge_capture_into_signal_payload
from .vnext.contract import KST, epoch
from .vnext.storage import publish, read

SCHEMA = 'q12_candidate_input.v1'


def input_path(reports_root, day):
    return Path(reports_root) / 'evaluation/baseline_btc_woori_tech' / day / 'q12_candidate_input.json'


def publish_input(*, day, reports_root, signals, candles, now_epoch):
    # Features only use current/past rows. Existing signal/ranking formulas unchanged.
    rows = [r for r in candles if epoch(day, '09:00') <= int(r.get('ts') or 0) <= min(now_epoch, epoch(day, '15:30'))]
    features = build_hypothesis_features(day=day, candles=rows, btc_signals=signals)
    payload = {'schema_version': SCHEMA, 'contract_id': HYPOTHESIS_CONTRACT_ID,
               'day': day, 'generated_epoch': now_epoch,
               'generated_at': datetime.fromtimestamp(now_epoch, KST).isoformat(),
               'features': features, 'delivery_owner': 'q12_input_worker',
               'btc_capture_status': signals.get('btc_0855_capture_status'),
               'candle_latest_epoch': max((int(r.get('ts') or 0) for r in rows), default=None)}
    publish(input_path(reports_root, day), payload)
    return payload


def load_candidate_input(*, reports_root, day, now_epoch, legacy, capture_root=DEFAULT_ROOT):
    """Read local files only. Canonical BTC cannot wait for Woori/report generation."""
    path = input_path(reports_root, day)
    payload = deepcopy(legacy or {})
    if path.exists():
        try:
            current = read(path)
            generated = int(current.get('generated_epoch') or 0)
            if current.get('schema_version') != SCHEMA or current.get('day') != day or generated > now_epoch:
                raise ValueError('input_schema_or_time_mismatch')
            payload = current
            if now_epoch - generated > 90:
                window_closed = now_epoch > epoch(day, '09:12')
                payload['delivery_status'] = 'WINDOW_CLOSED' if window_closed else 'INPUT_DELAY'
                payload['delivery_reason'] = (
                    'q12_opening_candidate_window_closed'
                    if window_closed else 'q12_candidate_input_stale'
                )
                payload.setdefault('features', {})['entry_methods'] = {}
            else:
                payload['delivery_status'] = 'CURRENT'
        except Exception:
            payload = {'day': day, 'features': {}, 'delivery_status': 'INPUT_DELAY',
                       'delivery_reason': 'q12_candidate_input_invalid'}
    snapshot_path = capture_paths(day, root=capture_root)['snapshot']
    if snapshot_path.exists():
        try:
            snapshot = read(snapshot_path)
            if snapshot.get('day') != day or int(snapshot.get('target_epoch') or 0) != epoch(day, '08:55') or now_epoch < epoch(day, '08:55'):
                raise ValueError('capture_day_or_time_mismatch')
            signals = merge_capture_into_signal_payload({}, day=day, root=capture_root)
            btc = _btc_0855(signals, day=day)
        except Exception:
            btc = {'status': 'MISSING', 'reason': 'btc_0855_capture_invalid'}
        payload.setdefault('features', {})['btc_0855'] = btc
        payload['btc_delivery_source'] = str(snapshot_path)
    return payload


def merge_fresh_btc_into_preserved_report(existing, signals, day):
    """Correct BTC status without discarding already-observed local evidence."""
    value = deepcopy(existing)
    if signals.get('btc_0855_capture_status') == 'CAPTURED':
        fresh = _btc_0855(signals, day=day)
        if fresh.get('status') == 'OBSERVED':
            value.setdefault('features', {})['btc_0855'] = fresh
            value['btc_delivery_source'] = 'canonical_0855_capture'
    return value
