from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from libs.reporting.baseline_btc_woori_tech.hypothesis_features import build_hypothesis_features
from libs.reporting.baseline_btc_woori_tech.vnext.contract import KST, epoch
from libs.reporting.baseline_btc_woori_tech.vnext.equities import confirmation, session_return
from libs.reporting.baseline_btc_woori_tech.vnext.features import build_features, classify
from libs.reporting.baseline_btc_woori_tech.vnext.outcomes import forward
from libs.reporting.baseline_btc_woori_tech.vnext.pipeline import build_vnext
from libs.reporting.baseline_btc_woori_tech.vnext.storage import read

DAY = '2026-09-07'


def fixture():
    target = epoch(DAY, '08:55')
    daily = [{'ts': target - 86400 * i - 8*3600 - 55*60, 'close': 100, 'high': 102} for i in range(130, 0, -1)]
    point = {'ts': target, 'price': 110, 'momentum_24h_pct': 5, 'momentum_5m_pct': .2,
             'momentum_15m_pct': .5, 'momentum_60m_pct': 1}
    signals = {'btc_0855_capture_status': 'CAPTURED', 'btc_0855_captured_sources': {'btc_usd': [point]},
               'crypto_time_alignment': {'status': 'AVAILABLE', 'btc_equity_interval_return_pct': 5, 'us_close_btc_price': 108, 'gap_type': 'WEEKEND'},
               'research_context': {'btc_usd_daily': daily, 'woori_daily': [{'ts': epoch('2026-09-04', '09:00'), 'close': 100}]}}
    candles = [{'ts': epoch(DAY, '09:00') + i*60, 'open': 101+i*.1, 'close': 101+i*.1,
                'high': 102+i*.1, 'low': 100+i*.1, 'volume': 100+i*100} for i in range(391)]
    equities = {t: {'status': 'OBSERVED', 'return_pct': 6} for t in ('COIN', 'MSTR')}
    return signals, candles, equities


@pytest.mark.parametrize('coin,mstr,expected', [(6,5,'STRONG'),(1,2,'CONFIRM'),(-2,-3,'DIVERGENCE'),(-1,2,'MIXED'),(None,2,'UNKNOWN')])
def test_equity_confirmation(coin, mstr, expected):
    assert confirmation({'COIN': {'status':'OBSERVED','return_pct':coin}, 'MSTR':{'status':'OBSERVED','return_pct':mstr}}, 5) == expected


def test_holiday_and_stale_session_not_reused():
    rows = [{'session':'2026-09-03','close':100}, {'session':'2026-09-04','close':105}]
    assert session_return(rows, '2026-09-07')['return_pct'] == pytest.approx(5)
    assert session_return(rows, '2026-09-08')['status'] == 'UNKNOWN'  # Labor Day close absent


def test_features_deterministic_no_lookahead():
    signals, candles, eq = fixture()
    at = epoch(DAY, '09:05')
    f, _ = build_features(DAY, signals, candles, eq, at)
    assert f['btc_daily_context']['market_state'] == 'FIRST_SURGE'
    assert f['btc_daily_context']['breakout_state'] == '120D_HIGH_BREAKOUT'
    assert f['btc_daily_context']['breakout_ath'] is None
    assert f['woori_opening']['opening_gap_pct'] == pytest.approx(1)
    assert f['entry_methods']['09:03']['confirmation'] == 'CONFIRMED'
    assert f['entry_methods']['09:05']['confirmation'] == 'CONFIRMED'
    changed = deepcopy(candles)
    for r in changed:
        if r['ts'] > at:
            r.update(open=999,close=999,high=999,low=999)
    assert build_features(DAY, signals, changed, eq, at)[0] == f
    signals['research_context']['btc_usd_daily'][-1]['close'] = 104
    assert build_features(DAY, signals, candles, eq, at)[0]['btc_daily_context']['market_state'] == 'EXTENDED'


def test_missing_capture_and_minute_fail_closed():
    signals, candles, eq = fixture()
    signals['btc_0855_capture_status'] = 'MISSED'
    candles = [r for r in candles if r['ts'] != epoch(DAY, '09:02')]
    f, _ = build_features(DAY, signals, candles, eq, epoch(DAY, '09:05'))
    assert f['btc_0855']['status'] == 'MISSING'
    assert f['entry_methods']['09:03']['confirmation'] == 'UNKNOWN'


def test_exact_forward_and_cost_mfe_mae():
    signals, candles, eq = fixture()
    entry = {'status':'OBSERVED','entry_epoch':epoch(DAY,'09:00'),'entry_price':101}
    result = forward(DAY, entry, candles, .35, epoch(DAY, '15:31'))
    r = result['09:30']
    assert r['gross_return_pct'] == pytest.approx((104/101-1)*100)
    assert r['net_return_pct'] == pytest.approx(r['gross_return_pct']-.35)
    assert r['mfe_pct'] == pytest.approx((104.9/101-1)*100)
    assert r['mae_pct'] == pytest.approx((100/101-1)*100)
    assert forward(DAY, entry, candles[:30], .35, epoch(DAY,'10:00'))['09:30']['status'] == 'MISSING_EVIDENCE'
    assert result['EOD']['status'] == 'OBSERVED'


def test_ab_immutable_no_broker_and_restart(tmp_path, monkeypatch):
    signals, candles, eq = fixture()
    original = deepcopy(signals)
    control = {'day':DAY,'features':build_hypothesis_features(day=DAY, candles=candles, btc_signals=signals)}
    from libs.execution.executors.real_executor import RealExecutor
    def no_broker(*args, **kwargs):
        pytest.fail('shadow invoked broker')
    monkeypatch.setattr(RealExecutor, 'execute', no_broker)
    args = dict(day=DAY,reports_root=tmp_path,signals=signals,candles=candles,control_payload=control,cost_pct=.3,slippage_pct=.05)
    build_vnext(**args, allow_fetch=True, equity_loader=lambda day:eq, now=datetime(2026,9,7,8,54,tzinfo=KST))
    result = build_vnext(**args, now=datetime(2026,9,7,9,5,tzinfo=KST))
    folder = __import__('pathlib').Path(result['observation_path'])
    before = {p.name:p.read_bytes() for p in folder.glob('*.json')}
    build_vnext(**args, now=datetime(2026,9,7,10,1,tzinfo=KST))
    assert all((folder/k).read_bytes()==v for k,v in before.items())
    record = read(folder/'0905.json')
    assert record['A']['eligible'] is True
    assert record['B']['label'] == 'FAST_BUY_CANDIDATE'
    assert record['order_execution_allowed'] is False
    assert record['features']['woori_specific_event']['status'] == 'UNKNOWN'
    assert signals == original
    assert 'arm' in __import__('pathlib').Path(result['report_path']).read_text()


def test_missing_equities_does_not_change_a(tmp_path):
    signals,candles,eq=fixture()
    control={'day':DAY,'features':build_hypothesis_features(day=DAY,candles=candles,btc_signals=signals)}
    args=dict(day=DAY,reports_root=tmp_path,signals=signals,candles=candles,control_payload=control,cost_pct=.3,slippage_pct=.05)
    build_vnext(**args,allow_fetch=True,equity_loader=lambda d:{},now=datetime(2026,9,7,8,54,tzinfo=KST))
    result=build_vnext(**args,now=datetime(2026,9,7,9,5,tzinfo=KST))
    r=read(__import__('pathlib').Path(result['observation_path'])/'0905.json')
    assert r['A']['eligible']
    assert r['B']['evidence_status']=='INSUFFICIENT_EVIDENCE'


def test_past_day_not_rebuilt(tmp_path):
    result=build_vnext(day='2026-09-04',reports_root=tmp_path,signals={},candles=[],control_payload={},cost_pct=0,slippage_pct=0,
                       now=datetime(2026,9,7,9,tzinfo=KST))
    assert result['status']=='SKIPPED'
    assert not list(tmp_path.iterdir())


def test_company_event_is_shadow_only_and_point_in_time():
    signals,candles,eq=fixture()
    signals['woori_specific_event']={'symbol':'041190','adverse':True,'source':'fixture','event_id':'x','observed_epoch':epoch(DAY,'09:04')}
    before,_=build_features(DAY,signals,candles,eq,epoch(DAY,'09:03'))
    after,_=build_features(DAY,signals,candles,eq,epoch(DAY,'09:05'))
    assert before['woori_specific_event']['status']=='UNKNOWN'
    assert classify(after,'09:05')['reason']=='structured_company_adverse_evidence_shadow_only'


def test_corrupt_context_is_not_overwritten(tmp_path):
    signals,candles,eq=fixture()
    args=dict(day=DAY,reports_root=tmp_path,signals=signals,candles=candles,control_payload={},cost_pct=0,slippage_pct=0)
    build_vnext(**args,allow_fetch=True,equity_loader=lambda d:eq,now=datetime(2026,9,7,8,54,tzinfo=KST))
    path=next(tmp_path.rglob('preopen_context.json'))
    path.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='schema_mismatch'):
        build_vnext(**args,now=datetime(2026,9,7,9,5,tzinfo=KST))
    assert path.read_text()=='{}'
