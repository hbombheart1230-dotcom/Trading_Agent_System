import json
import multiprocessing
import os
from copy import deepcopy
from types import SimpleNamespace

import pytest

from graphs.nodes.execute_from_packet import _normalize_execution, execute_from_packet
from libs.execution.intent_execution_owner import execute_owned_order
from libs.execution.intent_identity import bind_intent
from libs.supervisor.intent_state_store import SQLiteIntentStateStore


class Executor:
    def __init__(self, outcome='ACCEPTED'):
        self.calls = 0
        self.outcome = outcome

    def execute(self, request):
        self.calls += 1
        return SimpleNamespace(payload={'meta': {'broker_outcome': self.outcome}, 'order_id': '123'})


def order(iid='one', action='BUY'):
    return {'intent_id': iid, 'action': action, 'symbol': '005930', 'qty': 1,
            'price': 100, 'order_type': 'market'}


def submit(executor, iid='one', action='BUY', state=None):
    candidate = order(iid, action)
    return execute_owned_order(state=state or {'run_id': 'test'}, order=candidate,
        request=None, executor=executor, normalize=lambda result: _normalize_execution(
            allowed=True, execution_result=result, allow_result=None, order=candidate))


def test_normal_and_sequential_duplicate(monkeypatch):
    monkeypatch.setenv('EXECUTION_MODE', 'mock')
    ex = Executor()
    first = submit(ex)
    duplicate = submit(ex)
    assert first['broker_outcome'] == 'ACCEPTED'
    assert duplicate['broker_outcome'] == 'NOT_SENT'
    assert ex.calls == 1
    store = SQLiteIntentStateStore(os.environ['INTENT_STATE_DB_PATH'])
    assert store.get_state('one')['state'] == 'executed'
    assert [row['to_state'] for row in store.list_journal('one')] == ['pending_approval', 'approved', 'executing', 'executed']


@pytest.mark.parametrize('outcome,expected', [('REJECTED', 'failed'), ('UNKNOWN', 'executing')])
def test_failed_and_unknown_no_replay(monkeypatch, outcome, expected):
    monkeypatch.setenv('EXECUTION_MODE', 'mock')
    ex = Executor(outcome)
    submit(ex)
    assert submit(ex)['broker_outcome'] == 'NOT_SENT'
    assert ex.calls == 1
    assert SQLiteIntentStateStore(os.environ['INTENT_STATE_DB_PATH']).get_state('one')['state'] == expected


def test_backend_unavailable_zero_broker(monkeypatch, tmp_path):
    monkeypatch.setenv('INTENT_STATE_DB_PATH', str(tmp_path))  # directory, not DB
    ex = Executor()
    result = submit(ex)
    assert result['reason'] == 'intent_CAS_unavailable'
    assert result['broker_outcome'] == 'NOT_SENT'
    assert result['submission_attempts'] == 0
    assert ex.calls == 0


def test_different_ids_same_symbol_independent(monkeypatch):
    monkeypatch.setenv('EXECUTION_MODE', 'mock')
    ex = Executor()
    assert submit(ex, 'one')['ok']
    assert submit(ex, 'two')['ok']
    assert ex.calls == 2


@pytest.mark.parametrize('action', ['CANCEL', 'MODIFY'])
def test_cancel_modify_same_identity_no_replay(monkeypatch, action):
    monkeypatch.setenv('EXECUTION_MODE', 'mock')
    ex = Executor()
    assert submit(ex, 'child', action)['ok']
    assert submit(ex, 'child', action)['broker_outcome'] == 'NOT_SENT'
    assert ex.calls == 1


def _worker(db, barrier, queue):
    os.environ['INTENT_STATE_DB_PATH'] = db
    os.environ['EXECUTION_MODE'] = 'mock'
    ex = Executor()
    if barrier:
        barrier.wait()
    result = submit(ex)
    queue.put((ex.calls, result['broker_outcome']))


def test_real_multiprocess_and_restart(tmp_path):
    context = multiprocessing.get_context('spawn')
    db = str(tmp_path / 'concurrent.db')
    barrier, queue = context.Barrier(2), context.Queue()
    processes = [context.Process(target=_worker, args=(db, barrier, queue)) for _ in range(2)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(30)
        assert process.exitcode == 0
    results = [queue.get(timeout=5) for _ in processes]
    assert sum(calls for calls, _ in results) == 1
    restart = context.Process(target=_worker, args=(db, None, queue))
    restart.start()
    restart.join(30)
    assert restart.exitcode == 0
    assert queue.get(timeout=5) == (0, 'NOT_SENT')


def _crash_worker(db):
    os.environ['INTENT_STATE_DB_PATH'] = db
    os.environ['EXECUTION_MODE'] = 'mock'
    class CrashingExecutor:
        def execute(self, request):
            os._exit(0)  # Owner committed, no result can be persisted.
    submit(CrashingExecutor())


def test_real_process_crash_leaves_execution_owned(tmp_path, monkeypatch):
    db = str(tmp_path / 'crashed.db')
    monkeypatch.setenv('EXECUTION_MODE', 'mock')
    monkeypatch.setenv('INTENT_STATE_DB_PATH', db)
    process = multiprocessing.get_context('spawn').Process(target=_crash_worker, args=(db,))
    process.start()
    process.join(30)
    assert process.exitcode == 0
    assert SQLiteIntentStateStore(db).get_state('one')['state'] == 'executing'
    ex = Executor()
    assert submit(ex)['broker_outcome'] == 'NOT_SENT'
    assert ex.calls == 0


def test_terminal_write_failure_preserves_broker_truth(monkeypatch):
    monkeypatch.setenv('EXECUTION_MODE', 'mock')
    def broken(*args, **kwargs):
        raise OSError('disk unavailable after broker response')
    monkeypatch.setattr(SQLiteIntentStateStore, 'finish_execution', broken)
    ex = Executor()
    result = submit(ex)
    assert result['broker_outcome'] == 'ACCEPTED'
    assert result['reconciliation_required']
    assert result['intent_state_persistence_error'] == 'OSError'
    assert submit(ex)['broker_outcome'] == 'NOT_SENT'
    assert ex.calls == 1


def test_executing_crash_state_and_existing_pending_are_not_reapproved():
    store = SQLiteIntentStateStore(os.environ['INTENT_STATE_DB_PATH'])
    store.ensure_intent('one')
    ex = Executor()
    assert submit(ex)['broker_outcome'] == 'NOT_SENT'
    store.transition(intent_id='one', to_state='approved')
    store.transition(intent_id='one', to_state='executing', expected_from_state='approved')
    assert submit(ex)['broker_outcome'] == 'NOT_SENT'
    assert ex.calls == 0


def test_identity_provenance_and_payload_collision(monkeypatch):
    monkeypatch.setenv('EXECUTION_MODE', 'mock')
    state, intent, candidate = {'run_id': 'r1'}, {}, order('explicit')
    assert bind_intent(state, candidate, intent) == 'explicit'
    assert candidate['intent_id'] == intent['intent_id'] == state['intent_id']
    submit(Executor(), 'explicit')
    candidate['qty'] = 2
    ex = Executor()
    result = execute_owned_order(state=state, order=candidate, request=None, executor=ex,
        normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=candidate))
    assert result['reason'] == 'intent_identity_conflict'
    assert ex.calls == 0


def test_production_packet_path_duplicate_and_artifact_identity(tmp_path, monkeypatch):
    monkeypatch.setenv('EXECUTION_MODE', 'mock')
    monkeypatch.setenv('REPORTS_ROOT', str(tmp_path / 'reports'))
    cat = tmp_path / 'catalog.jsonl'
    cat.write_text(json.dumps({'api_id': 'ORDER_SUBMIT', 'method': 'POST', 'path': '/orders',
                              'params': {}, '_flags': {'callable': True}}))
    state = {'run_id': 'packet-owner', 'catalog_path': str(cat), 'decision_packet': {
        'intent': {**order('packet'), 'order_api_id': 'ORDER_SUBMIT'}, 'risk': {}, 'exec_context': {}}}
    ex = Executor()
    first = execute_from_packet({**deepcopy(state), 'executor': ex})
    second = execute_from_packet({**deepcopy(state), 'executor': ex})
    assert first['execution']['broker_outcome'] == 'ACCEPTED'
    assert second['execution']['broker_outcome'] == 'NOT_SENT'
    assert ex.calls == 1
    assert first['execution']['intent_id'] == first['execution']['order']['intent_id'] == 'packet'
    from libs.contracts.agent_outputs import build_executor_output_artifact, build_supervisor_output_artifact
    execution = first['execution']
    assert build_executor_output_artifact(first, execution=execution, order=execution['order'])['intent_id'] == 'packet'
    assert build_supervisor_output_artifact(first, order=execution['order'], allowed=True, reason='approved')['intent_id'] == 'packet'


def test_step5b_real_transport_composition(monkeypatch):
    from libs.catalog.api_request_builder import PreparedRequest
    from libs.core.http_client import HttpClient
    from libs.execution.executors.real_executor import RealExecutor
    from libs.kiwoom.kiwoom_token_client import EnsureTokenResult
    monkeypatch.setenv('EXECUTION_MODE', 'real')
    monkeypatch.setenv('KIWOOM_MODE', 'mock')
    monkeypatch.setenv('EXECUTION_ENABLED', 'true')
    monkeypatch.delenv('SYMBOL_ALLOWLIST', raising=False)
    http = HttpClient('https://example.test', retry_max=2, backoff_sec=0)
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        raise TimeoutError('broker accepted but client timed out')
    http.session = SimpleNamespace(request=request)
    ex = RealExecutor(http=http)
    ex.tokens = SimpleNamespace(ensure_token=lambda **kwargs: EnsureTokenResult(
        action='cache_hit', token='fake', expires_at_epoch=9999999999, reason='test'))
    candidate = order('transport')
    req = PreparedRequest('kt10000', 'POST', '/api/dostk/ordr', {}, {}, {'stk_cd': '005930', 'ord_qty': '1'})
    def run():
        return execute_owned_order(state={'run_id': 'transport'}, order=candidate, request=req, executor=ex,
            normalize=lambda r: _normalize_execution(allowed=True, execution_result=r, allow_result=None, order=candidate))
    assert run()['broker_outcome'] == 'UNKNOWN'
    assert run()['broker_outcome'] == 'NOT_SENT'
    assert len(calls) == 1
