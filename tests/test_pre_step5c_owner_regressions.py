import json
import multiprocessing
from datetime import datetime

import pytest

from libs.market import q10_index_observation_collector as c
from libs.reporting.baseline_samsung_hynix.forward_validation.reaction_reader import _index_reaction
from libs.runtime.controlled_mock_lanes.coordinator import _resolve_broker_outcome

DAY = '2026-09-04'


def now():
    return datetime.fromisoformat(DAY + 'T15:30:05+09:00')


def packet(timestamp='2026-09-04T15:30:03+09:00', finalized=True):
    return {'indices': {key: {'current': 110, 'current_date': '20260904',
            'market_observed_at': timestamp, 'session_finalized': finalized}
            for key in ('KOSPI', 'KOSDAQ')}}


@pytest.mark.parametrize('timestamp,finalized', [('bad', True), ('2026-09-04T15:15:00+09:00', True),
    ('2026-09-03T15:30:00+09:00', True), ('2026-09-04T15:30:03+09:00', 'false')])
def test_invalid_market_evidence_never_verified(tmp_path, timestamp, finalized):
    row = c.capture_slot(day=DAY, slot='15:30', root=tmp_path, now_fn=now,
                         capture=lambda: packet(timestamp, finalized))
    assert row['availability'] not in {'AVAILABLE', 'PARTIAL'}


@pytest.mark.parametrize('raw', ['{}', '[]', '{broken', json.dumps({'day': DAY, 'slots': None}),
    json.dumps({'day': DAY, 'slots': [{'requested_slot': 'wrong'}]})])
def test_existing_invalid_manifest_never_fresh(tmp_path, raw):
    path = c._manifest_path(DAY, root=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(raw)
    row = c.capture_slot(day=DAY, slot='15:30', root=tmp_path, now_fn=now,
                         capture=lambda: pytest.fail('must not query'))
    assert row['availability'] == 'CORRUPT_STATE'


def test_failed_measurement_is_not_absent(tmp_path):
    c.capture_slot(day=DAY, slot='15:30', root=tmp_path, now_fn=now, capture=lambda: {})
    result = _index_reaction(day=DAY, target={'symbol': 'KOSPI'},
        rows=[{'ts': int(now().timestamp()) - 5, 'close': 90}], collector_root=tmp_path)
    assert result['points']['CLOSE']['integrity_failure']


def test_one_authority_for_display_and_calculation(tmp_path):
    c.capture_slot(day=DAY, slot='15:30', root=tmp_path, now_fn=now, capture=packet)
    rows = [{'ts': int(datetime.fromisoformat(DAY + 'T09:00:00+09:00').timestamp()),
             'open': 100, 'close': 100, 'volume': 10}, {'ts': int(now().timestamp()) - 5, 'close': 90}]
    result = _index_reaction(day=DAY, target={'symbol': 'KOSPI'}, rows=rows, collector_root=tmp_path)
    assert result['points']['CLOSE']['price'] == 110
    assert result['forward_windows']['09:00']['return_to_close_pct'] == 10


def _capture_worker(root, barrier, queue, slot):
    barrier.wait()
    def capture():
        queue.put('api')
        return packet()
    c.capture_slot(day=DAY, slot=slot, root=root, now_fn=now, capture=capture)


@pytest.mark.parametrize('slots', [('15:30', '15:30'), ('09:30', '15:30')])
def test_os_process_claim_and_cross_slot_manifest(tmp_path, slots):
    context = multiprocessing.get_context('spawn')
    barrier, queue = context.Barrier(2), context.Queue()
    processes = [context.Process(target=_capture_worker, args=(str(tmp_path), barrier, queue, slot)) for slot in slots]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    rows = c.load_observations(DAY, root=tmp_path)
    assert len(rows) == len(set(slots))
    assert sum(row['logical_capture_attempt_count'] for row in rows) == len(set(slots))
    for slot in set(slots):
        c.capture_slot(day=DAY, slot=slot, root=tmp_path, now_fn=now,
                       capture=lambda: pytest.fail('restart replay'))


@pytest.mark.parametrize('execution', [{}, {'submission_phase': 'pre_submit', 'broker_message': 'rejected'},
    {'submission_phase': 'guard_blocked', 'order_id': '123', 'submission_attempts': 1},
    {'ok': True, 'submission_attempts': 1, 'broker_message': 'timeout'}, {'allowed': False}])
def test_ambiguous_fallback_is_unknown(execution):
    assert _resolve_broker_outcome(execution) == 'UNKNOWN'
