from copy import deepcopy
from datetime import datetime
from pathlib import Path
import threading

import pytest

from libs.reporting.baseline_btc_woori_tech.input_delivery import (
    load_candidate_input, merge_fresh_btc_into_preserved_report, publish_input, input_path,
)
from libs.reporting.baseline_btc_woori_tech.point_in_time_capture import capture_q12_btc_0855_snapshot
from libs.reporting.baseline_btc_woori_tech.vnext.contract import KST, epoch, VERSION, PREVIOUS_VERSION
from libs.reporting.baseline_btc_woori_tech.vnext.time_alignment import capture_alignment, session_context, project_alignment
from libs.reporting.baseline_btc_woori_tech.vnext.equities import confirmation
from libs.reporting.baseline_btc_woori_tech.vnext.storage import publish, read
from libs.runtime.controlled_mock_lanes.signals import build_q12_candidate

DAY = '2026-09-07'


def test_preopen_launch_is_scheduled_before_capture():
    root = Path(__file__).resolve().parents[1]
    registration = (root / 'scripts/register_mock_exam_tasks_example.bat').read_text(encoding='utf-8')
    launcher = (root / 'scripts/start_q12_preopen.ps1').read_text(encoding='utf-8')
    assert '%TASK_PREFIX%-Q12-Preopen' in registration and '/ST 08:45' in registration
    assert '%TASK_PREFIX%-Q12-BTC-0855' in registration and '/ST 08:55' in registration
    assert 'run_baseline_btc_woori_tech.py' in launcher
    assert '-WindowStyle Hidden' in launcher
    assert 'already_running' in launcher and "'--day', $day" in launcher


def signals():
    point = {'ts': epoch(DAY, '08:54'), 'price':110, 'momentum_24h_pct':5}
    return {'btc_0855_capture_status':'CAPTURED', 'btc_0855_captured_sources':{'btc_usd':[point]},
            'sources':{'btc_usd':[point]}, 'research_context':{'btc_usd_daily':[
                {'ts':epoch(DAY,'08:55')-86400*i,'close':100,'high':102} for i in range(65,0,-1)],
                'woori_daily':[{'ts':epoch('2026-09-04','09:00'),'close':100}]}}


def candles():
    return [{'ts':epoch(DAY,'09:00')+60*i,'open':101+i,'close':101+i,'high':102+i,'low':100+i,'volume':100*(i+1)} for i in range(6)]


def capture(root):
    capture_q12_btc_0855_snapshot(day=DAY, root=root, now=datetime(2026,9,7,8,55,1,tzinfo=KST),signal_loader=lambda **_: signals())


def test_monday_compares_same_interval_not_weekend_btc():
    context=session_context(DAY)
    assert context['session']=='2026-09-04'
    assert context['age_hours']==pytest.approx(51+55/60)
    assert context['gap_type']=='WEEKEND'
    equities={t:{'status':'OBSERVED','session':'2026-09-04','previous_session':'2026-09-03','return_pct':-5} for t in ('COIN','MSTR')}
    refs=[{'ts':context['us_previous_close_epoch'],'open':100}, {'ts':context['us_close_epoch'],'open':95}]
    aligned=project_alignment(capture_alignment(DAY,equities,refs),110)
    assert aligned['btc_equity_interval_return_pct']==pytest.approx(-5)
    assert aligned['btc_since_us_close_pct']==pytest.approx((110/95-1)*100)
    assert confirmation(equities,aligned['btc_equity_interval_return_pct'])=='STRONG'
    assert confirmation(equities,5)=='DIVERGENCE'  # The defective mixed-time comparison.
    assert capture_alignment(DAY,equities,[])['status']=='UNKNOWN'


def test_holiday_dst_and_short_session():
    assert session_context('2026-09-08')['reason']=='US_MARKET_HOLIDAY'
    assert session_context('2026-03-09')['us_close_kst'].startswith('2026-03-07T06:00')
    assert session_context('2026-03-10')['us_close_kst'].startswith('2026-03-10T05:00')
    assert session_context('2026-11-30')['us_close_kst'].startswith('2026-11-28T03:00')


def test_capture_visible_before_any_woori_candles(tmp_path):
    root=tmp_path/'capture'
    capture(root)
    legacy={'features':{'btc_0855':{'status':'MISSING'},'entry_methods':{}}}
    before=deepcopy(legacy)
    value=load_candidate_input(reports_root=tmp_path,day=DAY,now_epoch=epoch(DAY,'08:56'),legacy=legacy,capture_root=root)
    assert value['features']['btc_0855']['status']=='OBSERVED'
    assert value['features']['btc_0855']['return_24h_pct']==5
    assert not build_q12_candidate(value,now_epoch=epoch(DAY,'08:56'))
    assert legacy==before


@pytest.mark.parametrize('clock',['09:03','09:05'])
def test_light_input_ready_without_report_generation(tmp_path,clock):
    root=tmp_path/'capture'
    capture(root)
    payload=publish_input(day=DAY,reports_root=tmp_path,signals=signals(),candles=candles(),now_epoch=epoch(DAY,clock))
    loaded=load_candidate_input(reports_root=tmp_path,day=DAY,now_epoch=epoch(DAY,clock),legacy={},capture_root=root)
    candidate=build_q12_candidate(loaded,now_epoch=epoch(DAY,clock))
    assert candidate and candidate['evidence']['entry_method']==clock
    assert build_q12_candidate(payload,now_epoch=epoch(DAY,clock))==candidate
    assert not list(tmp_path.rglob('q12_btc_woori_hypothesis_validation.json'))


def test_stale_or_corrupt_input_never_authorizes(tmp_path):
    root=tmp_path/'capture'
    capture(root)
    publish_input(day=DAY,reports_root=tmp_path,signals=signals(),candles=candles(),now_epoch=epoch(DAY,'09:05'))
    value=load_candidate_input(reports_root=tmp_path,day=DAY,now_epoch=epoch(DAY,'09:07'),legacy={},capture_root=root)
    assert value['delivery_status']=='INPUT_DELAY'
    assert build_q12_candidate(value,now_epoch=epoch(DAY,'09:07')) is None
    input_path(tmp_path,DAY).write_text('{}')
    value=load_candidate_input(reports_root=tmp_path,day=DAY,now_epoch=epoch(DAY,'09:07'),legacy={},capture_root=root)
    assert value['delivery_status']=='INPUT_DELAY'


def test_preserved_report_receives_btc_without_losing_local_data():
    old={'features':{'btc_0855':{'status':'MISSING'},'entry_methods':{'09:03':{'status':'OBSERVED'}}}}
    value=merge_fresh_btc_into_preserved_report(old,signals(),DAY)
    assert value['features']['btc_0855']['status']=='OBSERVED'
    assert value['features']['entry_methods']==old['features']['entry_methods']
    assert old['features']['btc_0855']['status']=='MISSING'


def test_v1_evidence_preserved_on_v2_carry(tmp_path):
    from libs.reporting.baseline_btc_woori_tech.vnext.pipeline import build_vnext
    prior=tmp_path/'evaluation/baseline_btc_woori_tech/vnext'/PREVIOUS_VERSION/DAY/'preopen_context.json'
    publish(prior,{'day':DAY,'version':PREVIOUS_VERSION,'observed_at':f'{DAY}T08:38:33+09:00','daily_context':signals()['research_context'],'equities':{}})
    raw=prior.read_bytes()
    result=build_vnext(day=DAY,reports_root=tmp_path,signals=signals(),candles=candles(),control_payload={},cost_pct=0,slippage_pct=0,now=datetime(2026,9,7,10,tzinfo=KST))
    current=read(Path(result['validation_path']).parent/'preopen_context.json')
    assert current['version']==VERSION
    assert current['crypto_time_alignment']['status']=='UNKNOWN'
    assert prior.read_bytes()==raw


def test_input_worker_not_blocked_by_reporter(monkeypatch,tmp_path):
    from libs.reporting.baseline_btc_woori_tech import input_worker as worker
    done=threading.Event()
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026,9,7,9,3,tzinfo=KST)
    monkeypatch.setattr(worker,'datetime',Clock)
    def tick(self, now):
        publish_input(day=DAY,reports_root=tmp_path,signals=signals(),candles=candles(),now_epoch=now)
        done.set()
    monkeypatch.setattr(worker.InputWorker,'tick',tick)
    stop=worker.start_input_worker(day=DAY,reports_root=tmp_path,state_path=tmp_path/'state')
    try:
        assert done.wait(5)  # No invocation of the blocking report pipeline required.
        assert input_path(tmp_path,DAY).exists()
    finally:
        stop.set()
