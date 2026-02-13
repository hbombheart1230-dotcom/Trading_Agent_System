# M11-4 Logging & Daily Reports

- 날짜: 2026-02-11
- 목적: 모의 1~2달 운용 동안 **고도화에 쓸 수 있는 데이터**를 자동 축적한다.
- 핵심: run_id 단위로 (입력 스냅샷 → 피처/시그널 → 의사결정 → 감독관 판정 → 실행 결과)을 남긴다.

## 산출물
- `graphs/nodes/decide_trade.py`
  - `state['decision_trace']` 생성
  - features/signals/rationale/strategy 포함

- `graphs/nodes/log_decision_trace.py`
  - events.jsonl에 stage='decision', event='trace'로 기록

- `scripts/generate_daily_report.py`
  - events.jsonl을 읽어 일별 요약 리포트 생성
  - 출력: `reports/daily/daily_YYYY-MM-DD.md` / `.json`

## 운용 방법
- 파이프라인에 `log_decision_trace`를 `decide_trade` 직후에 추가 권장
- 매일 장 마감 후 아래 실행:
  - `python scripts/generate_daily_report.py`

## 다음
- (선택) decision_trace에 feature 확장: 변동성/거래대금/스프레드 등
- (선택) 리포트에 PnL / MDD 계산 추가 (실체결/평가손익 연동 시)
