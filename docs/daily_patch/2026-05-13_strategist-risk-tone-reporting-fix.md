# 2026-05-13 전략가 리스크 톤 리포팅 수정

## 배경

- `ai_trade_summary.md`의 `전략가 출력 요약`에서 `리스크 톤: -`로 표시되는 문제가 있었다.
- 실제 canonical 전략가 산출물에는 `decision_frame.risk_tone`, `strategy_frame.risk_tone`, `policy_selected.risk_tone`, 또는 `trace_summary.risk_tone` 값이 존재했다.
- 리포트 생성 경로는 주로 `strategist_trace_summary.risk_tone`만 확인했고, trace summary 생성 함수도 `risk_tone`을 안정적으로 포함하지 않았다.
- 운영 UI도 `summary.risk_tone`만 읽는 경로가 있어 같은 값이 비어 보일 수 있었다.

## 변경

- `libs/contracts/agent_outputs.py`
  - 전략가 trace summary에 `risk_tone`, `trade_aggressiveness`, `monitor_guidance`를 포함하도록 보강했다.

- `libs/reporting/trade_bundle_assembly.py`
  - 기존 trace summary가 있어도 `risk_tone`, `trade_aggressiveness`, `monitor_guidance`가 비어 있으면 `strategy_frame`, `policy_selected`, market context에서 보강한다.

- `libs/reporting/trade_report_ai.py`
  - trade report seed와 market context에 `risk_tone`, `trade_aggressiveness`, `monitor_guidance`를 전달한다.
  - canonical strategist trace, decision frame, strategy frame에 있는 값을 리포트 입력으로 끌어온다.

- `libs/reporting/trade_report_markdown_clean.py`
  - 리스크 톤 표시 우선순위를 `market.risk_tone -> strategist_trace_summary.risk_tone -> market.risk_mode`로 정리했다.

- `apps/operator_ui/data_access_core.py`
  - 운영 UI/브리프가 `summary`, `trace_summary`, `strategy_frame`, `policy_selected`, `decision_frame`, `market_context` 어디에 있는 값이든 `risk_tone`과 `monitor_guidance`를 회수하도록 보강했다.

## 검증

- `.\venv\Scripts\python.exe -m pytest tests/test_canonical_artifact_validation.py tests/test_trade_report_ai.py -q`
  - 결과: `150 passed`
- `py_compile`
  - `apps/operator_ui/data_access_core.py`
  - `libs/contracts/agent_outputs.py`
  - `libs/reporting/trade_bundle_assembly.py`
  - `libs/reporting/trade_report_ai.py`
  - `libs/reporting/trade_report_markdown_clean.py`

## 실행 상태

- live session 재시작 완료.
- lock 기준 PID: `1784`
- stderr: `0 bytes`
- `run_session.py`가 부모/자식 프로세스로 2개 보이는 것은 venv launcher와 실제 Python child 관계로 확인됐다.

## 남은 참고

- 과거에 이미 생성된 리포트는 재생성하지 않으면 기존 표시가 남을 수 있다.
- 새 리포트부터는 canonical 전략가 산출물의 `risk_tone=normal` 같은 값이 `리스크 톤: 보통`으로 표시되는 경로가 열린다.
