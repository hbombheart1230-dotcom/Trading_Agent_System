# 2026-05-09 Weekend Validation and Report Regeneration Review

## 목적

장외/주말 점검으로 2026-04-29부터 2026-05-08까지의 daily patch note를 다시 훑고, 검증 완료 사항과 남은 리스크를 정리했다. 추가로 2026-05-08 daily report 재생성이 10분 안에 끝나지 않았던 병목을 실제 코드 경로에서 줄였다.

## 검증 완료로 볼 수 있는 항목

- 2026-04-30 entry gate/reporting/memory default 정리: 테스트와 리포트 산출 경로가 유지된다.
- 2026-05-05 Truth Surface summary alignment: daily/operator summary에서 Truth Surface 기준을 쓰는 방향은 닫힌 상태다.
- 2026-05-06 trade price truth refresh: broker truth, 시장지수 컨텍스트, 비용 패치 적용 경로는 코드/리포트 산출 기준으로 연결되어 있다.
- 2026-05-07 report cleanup: daily/weekly/monthly/symbol 패턴 문구 정리, cost drag와 stop loss 분리, bucketed trade report 구조는 테스트와 재생성 경로에서 유지된다.
- 2026-05-08 4-stage LLM artifact/contract alignment: 1차/2차 중심 구조와 3차/4차 advisory boundary는 문서와 코드 흐름이 맞춰졌다.
- 2026-05-08 buy order price propagation, closeout residual position reporting, Friday/weekend carry guard, expected exit cost floor guard는 산출물 경로에 반영되어 있다.
- 2026-05-09 report regeneration patch: 2026-05-08 full daily report 재생성이 warm cache 기준 7.94초에 완료됐다.

## 아직 장중 검증이 필요한 항목

- 2026-04-29 runtime no-trade/open 항목은 계속 open이다. 정상 거절, 후보 미성숙, runtime stop/restart 이슈를 장중 이벤트로 더 구분해야 한다.
- 2026-05-04 AI report summary 문장 품질과 missing value rate metric은 partially closed다. 리포트 문구는 개선됐지만 누락률 자체를 daily summary에서 정량 추적하는 항목은 남아 있다.
- 비용 반영 패치는 live fill 이후에도 확인이 필요하다. 특히 가격은 소폭 상승했는데 세금/수수료로 net loss가 되는 거래가 `stop_loss`로 뭉개지지 않는지 계속 봐야 한다.
- Stage 2 post-scanner refresh는 무조건 중요 경로다. 실제 장중에서 1순위/차순위 후보 정보와 종목 메모리가 함께 들어가는지 artifacts로 확인해야 한다.
- Stage 3/4는 advisory 성격이 강하다. 오래 보유, 장마감/오버나이트, 주말 carry 판단이 룰베이스만으로 닫히지 않고 LLM artifact까지 남는지 다음 장에서 확인해야 한다.
- 다중 보유/동일 종목 중복 금지 흐름은 실계좌/모의계좌 포지션 스냅샷과 리포트 잔여 종목이 같은지 장중 검증해야 한다.

## Report Regeneration 병목 원인

기존 `scripts/generate_daily_report.py`는 daily report 하나를 만들 때 다음 무거운 작업을 반복했다.

- `data/logs/events.jsonl` 전체를 여러 번 JSON 파싱했다. 현재 파일은 약 2.1GB다.
- `generate_daily_report`, `generate_metrics_report`, `operator_visibility`, `policy_surface_quality`가 같은 날짜 이벤트를 각자 다시 읽었다.
- `collect_symbols_for_day`가 이미 만든 trade index를 재사용하지 않고 다시 trade lifecycle을 훑었다.
- `build_daily_trade_index`가 특정 날짜만 필요해도 전체 `reports/trades` 아래 lifecycle을 스캔했다.
- symbol trade report를 매번 재생성했다. 종목 수가 많거나 강제 refresh일 때 특히 느려진다.

## 적용한 개선

- `libs/reporting/event_log_reader.py` 추가: 날짜 지정 시 ISO timestamp raw line을 먼저 거르고, 날짜별 이벤트 JSONL cache를 만든다.
- `scripts/generate_daily_report.py`: 날짜 지정 재생성에서 day-filtered event reader를 사용한다.
- `scripts/generate_metrics_report.py`: metrics report도 같은 day-filtered event reader를 사용한다.
- `libs/reporting/operator_visibility.py`: operator summary snapshot 생성 시 같은 날짜 이벤트만 읽는다.
- `scripts/check_phase_5_2_5_3_runtime_health.py`: policy surface/runtime health 확인 시 같은 날짜 이벤트 cache를 사용한다.
- `libs/reporting/symbol_trade_report.py`: `build_daily_trade_index`가 해당 날짜 trade root만 읽고, `collect_symbols_for_day`는 이미 계산한 trade index를 재사용할 수 있게 했다.
- symbol report refresh 기본값을 `missing_or_stale`로 두었다. `DAILY_REPORT_SYMBOL_REPORT_MODE=always`를 주면 강제 재생성, `skip`을 주면 전부 생략할 수 있다.

## 측정 결과

- 기존 기록: 2026-05-08 full `scripts/generate_daily_report.py`가 10분 안에 완료되지 않음.
- 패치 후 중간 측정: 60.49초, 이후 cache와 day-root index 적용 후 37.63초.
- 최종 warm cache 측정: `REPORT_DAY=2026-05-08 venv\Scripts\python.exe scripts\generate_daily_report.py`가 7.94초 완료.
- 주요 내부 측정:
  - day event read: 1.12초
  - daily trade index: 0.03초
  - collect symbols: 0.71초
  - operator summary snapshot: 4.01초
  - policy surface quality: 1.37초

## 추가 개선 후보

- 이벤트 로그는 runtime 기록 시점부터 날짜별 파일도 같이 쓰는 구조가 가장 좋다. 지금 cache는 재생성 시간은 줄이지만, 원본 로그가 append되면 첫 실행은 다시 원본을 한 번 훑어야 한다.
- daily report CLI에 `--profile`, `--symbol-report-mode`, `--skip-policy-surface` 같은 명시 옵션을 추가하면 장중 빠른 확인과 마감 후 full rebuild를 분리할 수 있다.
- `symbols_observed`에 `AAA` 같은 비상장/테스트성 symbol이 들어오는 경로가 보인다. operator summary에서는 KRX symbol 형식 필터를 추가하는 것이 좋다.
- symbol report `missing_or_stale` 판단은 trade history 포함 여부 기준이다. WAIT reason 같은 이벤트 인사이트까지 반드시 최신이어야 하면 강제 refresh 또는 별도 lightweight insight cache가 필요하다.
- operator summary snapshot은 아직 4초 정도 걸린다. 다음 성능 개선은 commander route summary와 metrics summary의 중복 계산 제거가 우선이다.

## 검증 명령

```powershell
venv\Scripts\python.exe -m pytest tests/test_event_log_reader.py tests/test_daily_report.py tests/test_symbol_trade_report.py -q --basetemp=.pytest-work-symbol-index-check
venv\Scripts\python.exe -m pytest tests/test_generate_metrics_report.py tests/test_operator_visibility_reports.py -q --basetemp=.pytest-work-visibility-metrics-check
venv\Scripts\python.exe -m pytest tests/test_check_phase_5_2_5_3_runtime_health.py tests/test_event_log_reader.py -q --basetemp=.pytest-work-runtime-health-cache-check
$env:REPORT_DAY='2026-05-08'; venv\Scripts\python.exe scripts\generate_daily_report.py
```

결과:

- related report tests: pass
- runtime health/event cache tests: pass
- 2026-05-08 daily report regeneration: pass, 7.94초

## 다음 장중 체크

- 첫 주문 이후 비용 반영 net edge가 실제 체결 기준으로 summary/trade report에 맞게 드러나는지 확인한다.
- 매도 후 가격 추적이 다음 minute data 수집 이후 checkpoint를 실제로 채우는지 확인한다.
- stage2 post-scanner refresh artifact가 selected symbol과 runner-up 후보 정보를 모두 포함하는지 확인한다.
- 장마감 잔여 보유 종목과 오버나이트/주말 carry 사유가 daily summary에서 바로 보이는지 확인한다.
