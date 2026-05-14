# 2026-05-12 scanner/monitor chart-fit verification

## 확인 대상

- 2026-05-11 after-close 패치의 스캐너/모니터 차트 지표 강화 적용 여부를 점검했다.
- 핵심 기대값:
  - Monitor: `chart_structure_features.human_chart_context`를 만들고 진입 점수와 판단 trace에 소비한다.
  - Scanner: `scanner_chart_fit_score`, `scanner_chart_fit_components`, `scanner_chart_fit_authority=soft_rank_bias_only`를 계산하고 순위에 bounded soft bias로만 반영한다.
  - Stage 2 post-scanner strategist refresh에는 후보 비교용 차트-fit 필드가 보존된다.

## 확인 결과

- 2026-05-12 trade lifecycle/input artifacts에는 `scanner_chart_fit_score`, `scanner_chart_fit_components`, `chart_structure_features`, `human_chart_context`, `entry_chart_score`가 기록되고 있었다.
- `ai_trade_report.json`의 상단 요약 객체만 보면 해당 필드가 잘 보이지 않는다. 원천 evidence는 `lifecycle_bundle.json`과 `ai_trade_report_input.json`에 더 충실하다.
- 최신 Stage 2 prompt 표본에서는 `scanner_chart_fit_*` 원 필드가 빠져 있었다. 원인은 Commander의 post-scanner 후보 압축 함수가 `entry_compatibility_score`와 `compatibility_bias`만 넘기고 chart-fit 세부 필드를 누락한 것이다.

## 패치

- `graphs/commander_runtime.py`
  - post-scanner 후보 compact payload에 다음 필드를 보존한다:
    - `scanner_chart_fit_score`
    - `scanner_chart_fit_penalty`
    - `scanner_chart_fit_authority`
    - `scanner_chart_fit_components`
    - `raw_entry_compatibility_bias`
    - `effective_entry_compatibility_bias`
- `libs/runtime/etf_deviation.py`
  - 일반주 키움 기본정보의 `dstr_rt`를 ETF 괴리율로 오인하지 않도록 제한했다.
  - ETF/ETN 계열로 식별된 경우에는 `dstr_rt` 괴리율 사용을 유지한다.

## 발견한 리스크

- 삼성전자 같은 일반주 metadata의 `dstr_rt=76.0`이 ETF premium으로 해석되어 `etf_deviation_bias=-0.08` 패널티가 붙을 수 있었다.
- 이 경우 스캐너의 차트-fit 검증 자체는 동작하지만, ETF 괴리율 오인이 ranking을 왜곡해 “차트 지표 강화가 잘못 먹는 것처럼” 보일 수 있다.

## 검증

- `venv\Scripts\python.exe -m py_compile libs\runtime\chart_structure_features.py libs\runtime\intraday_monitor_signals.py libs\runtime\etf_deviation.py graphs\nodes\scanner_node.py graphs\nodes\monitor_node.py graphs\commander_runtime.py`
- `venv\Scripts\python.exe -m pytest -q tests\test_chart_structure_features.py tests\test_strategy_horizon_feedback.py tests\test_intraday_monitor_signals.py tests\test_scanner_monitor_compatibility.py tests\test_etf_deviation.py tests\test_commander_post_scanner_context.py`

