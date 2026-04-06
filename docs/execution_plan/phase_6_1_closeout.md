# Phase 6-1 Closeout: Read-Model & Fact/Narrative Separation

## A. 목적
결정 시스템의 결과를 UI 및 하위 에이전트가 100% Deterministic하게 소비할 수 있도록 읽기 전용 모델(Read-Model)을 구축하고, 리포트 생성 시 Fact와 LLM Narrative의 경계를 완벽히 분리하여 환각(Hallucination) 리스크를 원천 차단한다.

## B. 완료된 범위
1. **Read-Model 구현:** `trade_read_model.py`, `symbol_read_model.py`, `daily_read_model.py` (진행/통합 완료)
2. **Fact/Narrative 분리:** `build_separated_report` 체계 도입. LLM에는 오직 Fact Payload만 전달.
3. **Fallback 보장:** LLM 장애 또는 `DRY_RUN` 시에도 Fact는 항상 정상 서빙되도록 `status: error/dry_run` 구조 확보.

## C. 실제 구현 파일 목록
- `libs/reporting/trade_read_model.py`
- `libs/reporting/symbol_read_model.py`
- `libs/reporting/fact_narrative_report.py`
- `libs/reporting/trade_report_ai.py`

## D. 검증/테스트 결과
- **PASS:** `test_fact_narrative_separation.py`, `test_trade_read_model.py`, `test_symbol_read_model.py`
- LLM 없이도 시스템이 정상 동작하며, 기존 `reports/trades/*` 구조를 전혀 훼손하지 않음 (Additive).

## E. 문서-코드-Env Alignment 상태
- 완전 일치. 어떠한 신규 Env 추가 없이 Code-owned Default로만 집계 로직을 완성함.

## F. 남은 Known Gaps & G. 다음 Phase로 넘길 항목
- UI 단에서 이 분리된 구조(Read-Model)를 시각화하는 작업은 Phase 6 밖(Phase 7 등)으로 이관.

## H. Close 선언문
**본 문서를 기점으로 Trading Agent System의 Phase 6-1 작업을 공식적으로 완료(Closed) 처리한다.**