# Phase 6-2 Closeout: Internal Consumption & Routing Alignment

## A. 목적
Phase 6-1에서 구축된 Read-Model과 분리형 Report 구조를 실제 내부 시스템(Strategist, Reporting Pipeline)에 결합하고, 공식화된 LLM Model Selection Policy에 따라 에이전트별 모델 라우팅을 엄격히 고정한다.

## B. 완료된 범위
1. **Strategist Input 전환:** Raw Event/Artifact 대신 `read_model_facts` (recent trades, symbol patterns) 기반으로 전략 우선순위 조정.
2. **Reporting Pipeline 통일:** `trade_report_ai`, `daily_report`, `operator_brief`의 최종 출력을 Fact+Narrative 구조로 통일.
3. **LLM Routing 정렬:** `PRIMARY` -> `FALLBACK` 루프 구현 (`strategist_node.py`) 및 역할별 환경변수(`OPENROUTER_MODEL_*`) 적용.

## C. 실제 구현 파일 목록
- `graphs/nodes/strategist_node.py`
- `libs/reporting/trade_report_ai.py`, `daily_report.py`, `operator_visibility.py`
- `config/.env.example`

## D. 검증/테스트 결과
- **PASS:** `test_llm_model_policy.py`, `test_phase_6_2_consumption.py`
- Primary 실패 시 Fallback으로 정상 이관되며, 이 이력이 `llm_call_trace` 아티팩트에 영구 기록됨.

## E. 문서-코드-Env Alignment 상태
- 완전 일치. 공식 Policy Env(`OPENROUTER_MODEL_TRADE_REPORT`, `AI_STRATEGIST_MODEL_PRIMARY` 등)를 최우선 적용하고, 레거시 환경 변수는 호환성 유지를 위해 하위 우선순위 폴백으로 남겨둠.

## F. 남은 Known Gaps & G. 다음 Phase로 넘길 항목
- Fallback 모델마저 실패하는 경우 발동하는 Strict Block(매매 중지)의 장기 통계 분석은 운영 모니터링(M25 등)에서 다룸.

## H. Close 선언문
**본 문서를 기점으로 Trading Agent System의 Phase 6-2 작업을 공식적으로 완료(Closed) 처리한다.**