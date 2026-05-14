# 2026-05-12 Human Chart Guard / Chart-Fit / Horizon Alignment

## 배경

장 마감 후 2026-05-12 리포트와 이벤트를 점검했다.

- 완료 거래 10건 중 확인 가능한 순손익 표본은 1승 4패였다.
- `064240`은 `entry_chart_score=0.16`, `vwap_breakdown_persistence=strong`, `exit_risk_score=0.42` 수준의 약한 차트 구조에서도 BUY가 나갔다.
- 스캐너의 `scanner_chart_fit_score`는 canonical scanner에는 남았지만 trade lifecycle/report 표면에는 충분히 전달되지 않았다.
- 전략가 `strategy_horizon`은 문서상 4옵션이지만 실제 LLM 응답과 commander policy에는 대부분 `scalp` / `intraday`만 남았다.

## 패치

### 1. Monitor human-chart BUY guard

`libs/runtime/intraday_monitor_signals.py`

- `human_chart_buy_guard.v1` 추가.
- 기존 `human_chart_context`를 최종 BUY 직전에 안전가드로 사용한다.
- 아래 조건은 BUY를 WAIT로 차단한다.
  - `vwap_breakdown_persistence=strong`
  - `exit_risk_score >= 0.40`
  - `entry_chart_score < 0.25`이면서 VWAP 회복이 부재하거나 강한 VWAP 이탈이 동반됨
  - `swing_low_break=true`
  - `lower_high_failure`인데 강한 VWAP 회복이 없음
  - `late_entry_risk=high`이면서 entry score가 약함
- 정상 pullback 샘플을 막지 않도록 `entry_chart_score` 단독으로는 차단하지 않는다.

### 2. Scanner chart-fit report propagation

`libs/reporting/trade_story_pipeline.py`  
`libs/reporting/trade_report_markdown_clean.py`

- `scanner_chart_fit_score`, `scanner_chart_fit_authority`, `scanner_chart_fit_components`를 `scanner_reason_human`, `scanner_selection_trace`, `top_candidates`, `runner_ups`에 전달한다.
- `ai_trade_summary_input.decision_flow`에 `scanner_chart_fit`, `scanner_chart_fit_score`, `scanner_chart_fit_authority`를 추가한다.
- `ai_trade_summary.md` 종목 선정 흐름에 `Scanner chart-fit` 라인을 표시한다.
- chart-fit이 0.25 미만이면 deterministic finding에 `scanner_chart_fit_low`를 남긴다.

### 3. Strategy horizon enum normalization

`libs/runtime/strategy_horizon_feedback.py`  
`graphs/nodes/strategist_node.py`

- LLM이 `scalp|intraday|overnight_probe|1_2day_swing` 같은 placeholder를 그대로 반환하면 invalid로 보고 deterministic fallback을 사용한다.
- alias 정규화:
  - `scalp_intraday` -> `scalp`
  - `swing_1_2day` -> `1_2day_swing`
- Stage prompt에 `strategy_horizon_feedback.strategy_horizon`은 반드시 `scalp`, `intraday`, `overnight_probe`, `1_2day_swing` 중 하나만 고르라고 명시했다.
- live validation 중 장기 horizon은 기존 정책대로 commander가 `intraday`로 cap할 수 있다. 강제 보유는 여전히 금지다.

## 검증

- `venv\Scripts\python.exe -m pytest -q tests\test_intraday_monitor_signals.py tests\test_strategy_horizon_feedback.py`
  - 76 passed
- `venv\Scripts\python.exe -m pytest -q tests\test_trade_story_pipeline_enrichment.py -k "scanner_reason_human"`
  - 2 passed
- `venv\Scripts\python.exe -m pytest -q tests\test_trade_report_ai.py -k "trade_summary or horizon"`
  - 17 passed
- `venv\Scripts\python.exe -m pytest -q tests\test_scanner_monitor_compatibility.py tests\test_commander_post_scanner_context.py`
  - 9 passed
- `venv\Scripts\python.exe -m pytest -q tests\test_m18_market_scan_candidates.py tests\test_m21_commander_runtime_entry.py`
  - 90 passed
- `venv\Scripts\python.exe -m py_compile ...`
  - passed

## 남은 리스크

- 새 monitor guard는 오늘 `064240` 같은 구조를 막기 위한 최소 차단이다. 실제 장중에는 정상 눌림목을 과차단하지 않는지 봐야 한다.
- scanner chart-fit은 아직 soft rank bias다. 리포트 visibility를 먼저 확보했고, 다음 단계에서 낮은 chart-fit 후보의 rank penalty 강화 여부를 판단한다.
- horizon 4옵션은 정규화와 표시 정합성은 개선됐지만, 장기 옵션을 실제 행동 변경으로 허용하지는 않는다. Stage4/EOD carry review가 정상 실행되는지 다음 장중/장마감에서 검증해야 한다.
