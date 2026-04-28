# AI Trade Report 운영자 가독성 개선 지시서

작성일: 2026-04-28  
대상: `ai_trade_report.md` / AI 거래 리포트 생성 로직  
목적: 운영자가 리포트를 읽고 즉시 개선점을 판단할 수 있도록 리포트 구조를 `결론 → 원인 → 평가 → 세부 근거` 순서로 재구성한다.

---

## 0. 현재 구현 기준

2026-04-28 패치 이후 운영자 가독성 개선은 `ai_trade_report.md` 단일 파일에 모두 밀어 넣지 않는다.

현재 역할 분리는 다음과 같다.

- `ai_trade_report.md`: 상세 lifecycle/audit 리포트. 기존 세부 근거를 유지한다.
- `ai_trade_summary_input.json`: summary LLM 입력. `ai_trade_report.json`에서 압축 생성한다.
- `ai_trade_summary.json`: summary LLM 평가 결론 저장.
- `ai_trade_summary.md`: 운영자가 먼저 읽는 요약 리포트.

따라서 이 문서의 “운영 요약을 최상단에 둔다”는 요구사항은 현재 구현에서 `ai_trade_summary.md`가 담당한다.  
`ai_trade_report.md`는 세부 감사 리포트로 유지하며, 상세 근거를 삭제하거나 과도하게 축약하지 않는다.

관련 현재 계약 문서:

- `trade_report_summary_llm_contract_2026-04-28.md`
- `report_regeneration_llm_mode_2026-04-25.md`

---

## 1. 개선 배경

현재 AI Trade Report는 canonical artifact, broker truth, strategist/scanner/monitor/supervisor/executor 근거를 폭넓게 담고 있어 디버깅과 감사 용도로는 충분하다.

하지만 운영자 관점에서는 다음 문제가 있다.

1. 핵심 결론이 하단 또는 중간에 흩어져 있어 빠르게 판단하기 어렵다.
2. 메모리, 전략가 입력, 정책 적용, 시장 설명이 중복되어 가독성이 떨어진다.
3. “무슨 일이 있었는지”는 많지만 “그래서 무엇을 개선해야 하는지”가 약하다.
4. 잘한 점 / 잘못한 점 / 원인 / 다음 액션이 한눈에 보이지 않는다.
5. 세부 근거는 반드시 보존해야 하지만, 처음부터 전부 노출될 필요는 없다.

따라서 리포트 목적을 다음처럼 명확히 한다.

> 이 문서는 전략가 입력용이 아니라, 운영자가 거래 결과를 읽고 시스템 개선 방향을 판단하기 위한 운영자용 리포트다.

---

## 2. 핵심 원칙

### 2.1 누락 금지

기존 리포트에 있던 핵심 정보는 삭제하지 않는다.

반드시 보존해야 할 정보:

- 거래 ID / 종목 / 라이프사이클 상태
- 생성 정보
- Truth Surface
- 전략가 입력 메모리
- 사후 복원 메모리
- 실제 적용된 메모리 bias
- 시장 환경
- 전략가 요약
- 전략가 refresh trace
- 전략가 출력 근거
- 선택 종목 상세 분석
- 스캐너 후보 비교
- 가드 승인 결과
- 진입 상세 근거
- 보유 경과
- 청산 판단 근거
- 모니터 스냅샷
- 실행 결과
- 결과 평가
- 보완 사안
- 근거 출처
- 전체 타임라인
- 최종 운영 판단

단, 동일 의미를 반복하는 문장은 합치고, 불필요한 장황한 표현은 제거한다.

### 2.2 운영자 판단 우선

리포트 최상단에는 반드시 다음을 둔다.

1. 거래 결과
2. 이번 거래가 왜 이렇게 됐는지
3. 잘한 점
4. 잘못한 점
5. 개선 우선순위
6. 세부사항은 아래 섹션을 보라는 안내

### 2.3 결론 먼저, 근거는 아래

현재 구조는 `데이터 → 설명 → 결론`에 가깝다.  
개선 구조는 반드시 다음 순서를 따른다.

```text
운영 요약
→ 거래 결과
→ 원인 해석
→ 잘한 점 / 잘못한 점
→ 개선 액션
→ 세부 근거
→ 원본 추적 정보
```

### 2.4 중복 제거

다음 유형의 반복을 줄인다.

- 같은 수익률/손익을 여러 섹션에서 반복
- 같은 시장 상태를 여러 문장으로 반복
- “전략가는 최종 종목을 선택하지 않는다” 같은 역할 설명 반복
- “기준으로 정리했습니다”류 문장 반복
- “확인해야 합니다”가 여러 번 이어지는 문장

### 2.5 이상한 문구 제거

다음처럼 부자연스럽거나 운영자 판단에 도움이 적은 문구는 정리한다.

- “시장 시장 상태”
- “진입 유지 판단이며, 매도 주문...”처럼 상충되어 보이는 표현
- “스캐너 최고 순위 후보”와 실제 순위/점수가 맞지 않는 표현
- “닫힌 거래 0건”과 “닫힌 거래 9건”처럼 시점이 다른 값이 섞일 때 설명 없는 병치
- fallback / unavailable을 단순 나열만 하고 의미를 설명하지 않는 문장

---

## 3. 목표 리포트 구조

아래 구조를 `ai_trade_report.md`의 목표 출력 형식으로 삼는다.

---

# AI 거래 리포트 (`{trade_id}`)

## 0. 운영 요약 (Operator Decision Summary)

### 0.1 결론

- 결과: `{win_loss}` / `{pnl}` / `{pnl_pct}`
- 거래 상태: `{lifecycle_status}`
- 실행 모드: `{execution_mode}`
- 한 줄 요약: `{operator_one_line_summary}`

예시:

> 이번 거래는 진입은 경계선에서 성립했지만, 보유 중 고점 대비 하락폭이 빠르게 확대되며 손실 청산됐다. 시스템은 정상 동작했으나, 진입 보수화와 청산 민감화가 동시에 작동해 손익 구조가 불리해졌다.

### 0.2 왜 이렇게 됐나

- 진입: `{entry_path}` / `{entry_reason}`
- 보유: `{holding_summary}`
- 청산: `{exit_reason}`
- 구조적 해석: `{cause_interpretation}`

예시:

- 진입은 VWAP 재회복과 돌파 조건으로 성립했다.
- 진입 신뢰도는 기준값과 거의 동일해 여유 있는 진입은 아니었다.
- 보유 중 고점 대비 하락폭이 커지며 peak drawdown 기준으로 청산됐다.
- 메모리 적용 결과 진입은 더 보수적으로, 청산은 더 민감하게 조정됐다.

### 0.3 잘한 점

- `{positive_1}`
- `{positive_2}`
- `{positive_3}`

예시:

- 브로커 체결가와 키움 당일 실현손익이 정상 연결되어 Truth Surface 신뢰도가 높다.
- 진입/청산 run_id가 연결되어 거래 라이프사이클 추적이 가능하다.
- Monitor, Supervisor, Executor 단계가 정상적으로 분리되어 실행 안전성은 유지됐다.

### 0.4 잘못된 점 / 취약점

- `{weakness_1}`
- `{weakness_2}`
- `{weakness_3}`

예시:

- 당일 반복 패턴상 Monitor 단독 경로와 차순위 재평가가 과도하게 반복됐다.
- 진입 기준은 보수화됐고 청산 기준은 더 타이트해져 손익비가 악화될 수 있다.
- 보유 구간의 중간 모니터 문맥이 부족해 청산 전후의 미세한 변화 추적이 어렵다.

### 0.5 개선 우선순위

1. `{priority_1}`
2. `{priority_2}`
3. `{priority_3}`

예시:

1. Exit 정책: peak_drawdown activation과 confirm 조건 재점검
2. Entry 정책: 경계선 진입이 반복되는지 확인
3. Scanner-Monitor 정합성: 1순위 탈락 후 차순위 진입 구조가 성과를 악화시키는지 점검

### 0.6 상세 확인 위치

- 가격/손익 확정값은 `1. Truth Surface` 참고
- 전략가 입력과 메모리 영향은 `3. 전략/메모리` 참고
- 종목 선정과 후보 비교는 `5. 스캐너/종목 선정` 참고
- 진입/보유/청산 세부 근거는 `6. 거래 라이프사이클` 참고
- 원본 로그와 provenance는 `9. 근거 출처` 참고

---

## 1. 거래 개요

- Trade ID: `{trade_id}`
- 종목: `{symbol}`
- 리포트 유형: `{report_type}`
- 라이프사이클 상태: `{lifecycle_status}`
- 실행 모드: `{execution_mode}`
- 생성 상태: `{generation_status}`
- 생성 방식: `{generation_method}`
- 사용 모델: `{model}`
- 생성 시각: `{generated_at}`

---

## 2. Truth Surface

### 2.1 확정 가격/손익

- 매수가: `{broker_buy_price}`
- 매도가: `{broker_sell_price}`
- 실현 손익: `{realized_pnl}`
- 실현 손익률: `{realized_pnl_pct}`
- 수수료: `{fee}`
- 세금: `{tax}`

### 2.2 기준 소스

- 가격 기준: `{price_truth_source}`
- 손익 기준: `{pnl_truth_source}`
- 브로커 손익 매칭 방식: `{broker_pnl_match_method}`
- 가용성 요약: `{availability_summary}`

운영 해석:

> 이 거래는 브로커 체결가와 키움 당일 실현손익 기준이 연결되어 있어 결과 판정의 신뢰도가 높다.

---

## 3. 전략 / 메모리 / 정책 영향

### 3.1 전략가 입력에 포함된 정보

- 전략 메모리: `{strategy_memory_available}`
- 메모리 패킷: `{memory_packet_available}`
- 지휘관 정책: `{commander_policy_available}`
- 종목 메모리: `{symbol_memory_available}`
- 리포터 피드백: `{reporter_feedback_available}`
- 읽기 모델: `{read_model_available}`

요약:

> 전략가 호출 시점에는 메모리와 리포터 피드백이 입력으로 제공됐지만, 실제 정책 반영 여부는 별도로 확인해야 한다.

### 3.2 사후 복원 메모리

- 복원 목적: `{post_restore_purpose}`
- 당일 닫힌 거래 집계: `{same_day_closed_trade_summary}`
- 원본 프롬프트 포함 여부: `{from_original_prompt_or_reconstructed}`

요약:

> 이 섹션은 전략가 원본 프롬프트가 아니라, 거래 설명을 위해 실행 기록에서 사후 복원한 운영자용 문맥이다.

### 3.3 실제 적용된 메모리 bias

- 전략가 입력 시점: `{strategist_memory_state}`
- 스캐너 적용: `{scanner_memory_application}`
- 모니터 적용: `{monitor_memory_application}`
- 최신 커맨더 상태: `{latest_commander_memory_state}`

정책 변화:

- Entry: `{entry_policy_delta}`
- Exit: `{exit_policy_delta}`

운영 해석:

> 이번 거래에서는 스캐너에는 메모리 bias가 적용되지 않았고, 모니터에는 종목 레벨 메모리가 적용됐다. 그 결과 진입은 더 보수적으로, 청산은 더 민감하게 조정됐다.

---

## 4. 시장 환경과 전략가 판단

### 4.1 시장 환경

- 국내 시장 상태: `{domestic_market_status}`
- 글로벌 시장 상태: `{global_market_status}`
- VIX: `{vix}`
- 글로벌 감성: `{global_sentiment}`
- 뉴스 입력: `{news_input_summary}`
- 테마 packet 상태: `{theme_packet_status}`

### 4.2 전략가 요약

- 시장 상태: `{market_regime}`
- 시장 심리: `{market_sentiment}`
- 플레이북: `{playbook}`
- 리스크 톤: `{risk_tone}`
- 모니터 가이드: `{monitor_guide}`
- 뉴스 활용 방식: `{news_usage}`

### 4.3 전략가 Refresh Trace

- 1차 전략 프레임: `{first_strategy_frame_status}`
- 2차 refresh 요청 여부: `{refresh_requested}`
- refresh 사유: `{refresh_reason}`
- 최종 정책 반영 여부: `{refresh_applied}`
- delta count: `{policy_delta_count}`
- 변경 후보 필드: `{policy_delta_fields}`

운영 해석:

> 전략가 refresh는 발생했지만 최종 정책 변화는 없었다. 따라서 이번 거래의 직접 원인은 refresh 결과보다 스캐너/모니터 단계의 선택 및 청산 정책에서 봐야 한다.

---

## 5. 스캐너 / 종목 선정

### 5.1 선택 종목 요약

- 실제 체결 종목: `{symbol}`
- 스캐너 순위: `{scanner_rank}`
- 후보 수: `{candidate_count}`
- 종합 점수: `{scanner_score}`
- 신뢰도: `{scanner_confidence}`
- 위험 점수: `{risk_score}`

선정 이유:

- `{selection_reason_1}`
- `{selection_reason_2}`
- `{selection_reason_3}`

### 5.2 후보 비교

- 1순위 후보: `{top_candidate}`
- 1순위 탈락 사유: `{top_candidate_block_reason}`
- 실제 진입 후보 전환 사유: `{fallback_or_reselection_reason}`
- 차순위 후보 요약: `{other_candidates_summary}`

운영 해석:

> 000660은 최초 1순위가 아니라 차순위 재평가를 통해 진입한 종목이다. 이 구조가 반복되면 Scanner의 상위 랭킹과 Monitor의 실제 진입 가능성이 어긋나고 있을 가능성이 있다.

---

## 6. 거래 라이프사이클

### 6.1 진입

- 진입 run_id: `{entry_run_id}`
- 진입 시각: `{entry_time}`
- 진입 액션: `{entry_action}`
- 진입 사유: `{entry_reason}`
- 진입 경로: `{entry_path}`
- 진입 신뢰도: `{entry_confidence}`
- 신뢰도 기준: `{entry_confidence_threshold}`
- 적용 정책: `{entry_policy_summary}`

게이트 상태:

- VWAP 재회복: `{vwap_reclaim_status}`
- 과확장 점검: `{extended_from_vwap_status}`
- 신뢰도 게이트: `{confidence_gate_status}`
- 거래량 조건: `{volume_condition_status}`
- 반등 확인: `{rebound_status}`

운영 해석:

> 진입은 성립했지만 신뢰도 점수가 기준값과 동일해 여유 있는 진입은 아니었다. 경계선 진입이 반복되는지 별도 집계가 필요하다.

### 6.2 보유 경과

- 보유 시간: `{holding_seconds}`
- 청산 직전 현재가: `{pre_exit_current_price}`
- 포지션 평균단가(모니터 신호 계산용): `{avg_price}`
- 고점: `{peak_price}`
- 모니터 기준 손익 변동: `{monitor_pnl_pct}`
- 고점 대비 하락폭: `{drawdown_from_peak_pct}`

운영 해석:

> 보유 중 고점은 형성됐으나 이를 수익으로 확정하지 못했고, 고점 대비 하락폭 기준으로 청산됐다.

### 6.3 청산

- 청산 run_id: `{exit_run_id}`
- 청산 액션: `{exit_action}`
- 정규화된 청산 사유: `{normalized_exit_reason}`
- 실제 청산 트리거: `{actual_exit_trigger}`
- 청산 직전 모니터 관측가: `{monitor_exit_price}`
- 실제 매도 체결가: `{broker_sell_price}`
- 유효 손절 기준: `{effective_stop_loss}`
- 기준 축: `{exit_threshold_axis}`

모니터가 함께 본 기준:

- 손절: `{stop_loss_threshold}`
- 목표 수익: `{take_profit_threshold}`
- 추적 손절: `{trailing_stop_threshold}`
- peak drawdown: `{peak_drawdown_threshold}`
- VWAP 이탈: `{vwap_break_status}`
- 장중 저점 이탈: `{intraday_low_break_status}`
- 추세 붕괴: `{trend_break_status}`

운영 해석:

> 청산은 고점 대비 하락폭 기준으로 실행됐다. 이번 거래에서는 고정 손절보다 peak drawdown 계열의 보유 관리가 더 중요한 설명 축이다.

주의: 청산 직전 현재가/포지션 평균단가/고점/모니터 기준 손익 변동은 모니터 신호 판단용 관측값이다. 실제 매수가, 매도가, 실현손익률, 수수료, 세금은 `Truth Surface`를 기준으로 표시해야 한다.

---

## 7. Supervisor / Executor 결과

### 7.1 승인 결과

- 감독 승인 판단: `{supervisor_decision}`
- 허용 여부: `{allowed}`
- 검토 액션: `{reviewed_action}`
- 가드 판단 사유: `{guard_reason}`

### 7.2 실행 결과

- 브로커 체결 가격: `{broker_execution_price}`
- 브로커 실현 손익: `{broker_realized_pnl}`
- 수수료 / 세금: `{fee}` / `{tax}`
- 가격 truth 소스: `{price_truth_source}`
- 손익 truth 소스: `{pnl_truth_source}`

운영 해석:

> Supervisor와 Executor는 정상 동작했다. 이번 거래의 개선 초점은 승인/실행 계층보다 진입/보유/청산 정책에 있다.

---

## 8. 당일 패턴과 결과 평가

### 8.1 당일 성과 요약

- 당일 닫힌 거래 수: `{same_day_closed_trades}`
- 승리 / 손실: `{wins}` / `{losses}`
- 평균 손익률: `{average_pnl_pct}`

### 8.2 반복 패턴

- Monitor 단독 경로: `{monitor_only_path_count}` / `{total_path_count}`
- 차순위 재평가 경로: `{reselection_path_count}` / `{total_path_count}`
- 주요 반복 no-trade 또는 blocker: `{dominant_blockers}`

### 8.3 리포터 권고

- `{reporter_recommendation_1}`
- `{reporter_recommendation_2}`
- `{reporter_recommendation_3}`

운영 해석:

> 단일 거래 손실보다 중요한 것은 당일 반복 패턴이다. Monitor 단독 경로와 차순위 재평가가 반복된다면, 후보 선정과 실제 진입 가능성 간 정합성을 먼저 점검해야 한다.

---

## 9. 보완 필요 사항

### 9.1 데이터 보존 보완

- 보유 구간 모니터 문맥 보강
- 동일 일자 리포터 분석 연결 강화
- 메모리 기반 정책 변화 provenance 강화

### 9.2 판단 로직 보완

- peak drawdown activation 조건 점검
- 경계선 진입 반복 여부 집계
- scanner rank와 monitor pass rate의 상관 점검

### 9.3 리포트 품질 보완

- fallback/unavailable 데이터는 단순 나열하지 말고 영향도를 함께 설명
- 전략가 입력 시점 값과 사후 복원 값을 명확히 분리
- 중복 문장 제거

---

## 10. 근거 출처 / Provenance

### 10.1 데이터 출처 요약

- 주요 데이터 출처: `{primary_data_source}`
- 보조 데이터 출처: `{secondary_data_source}`
- fallback 사용 여부: `{fallback_used}`
- unavailable 항목: `{unavailable_items}`

### 10.2 참조 경로

- Commander: `{commander_json_path}`
- Strategist: `{strategist_json_path}`
- Scanner: `{scanner_json_path}`
- Monitor: `{monitor_json_path}`
- Supervisor: `{supervisor_json_path}`
- Executor: `{executor_json_path}`

### 10.3 신뢰도

- Truth Surface 신뢰도: `{truth_confidence}`
- 전략/메모리 해석 신뢰도: `{strategy_memory_confidence}`
- 보유 구간 해석 신뢰도: `{holding_confidence}`
- 전체 리포트 신뢰도: `{overall_report_confidence}`

---

## 11. 전체 타임라인

- 진입: `{entry_run_id}` / `{entry_time}` / `{entry_summary}`
- 청산: `{exit_run_id}` / `{exit_time}` / `{exit_summary}`

---

## 12. 최종 운영 판단

- 현재 상태: `{final_status}`
- 최종 액션: `{final_action}`
- 다음 확인 항목:
  - `{next_check_1}`
  - `{next_check_2}`
  - `{next_check_3}`
- 기존 판단이 무효화되는 조건:
  - `{invalidation_condition_1}`
  - `{invalidation_condition_2}`
  - `{invalidation_condition_3}`

최종 문장 예시:

> 이번 거래는 시스템 장애가 아니라 정책 조합과 거래 구조의 문제로 보는 것이 타당하다. 특히 진입은 경계선에서 성립했고, 청산은 고점 대비 하락폭 기준으로 빠르게 실행됐다. 다음 개선은 실행 계층이 아니라 Monitor의 보유/청산 정책과 Scanner-Monitor 정합성 점검에 집중해야 한다.

---

## 4. 현재 샘플 리포트 기준 적용 예시

아래는 `TRD_20260428_000660_02` 샘플에 위 구조를 적용했을 때의 축약 예시다.

---

# AI 거래 리포트 (`TRD_20260428_000660_02`)

## 0. 운영 요약 (Operator Decision Summary)

### 0.1 결론

- 결과: 손실
- 실현 손익: -12,829원 / -0.97%
- 거래 상태: 청산 완료
- 실행 모드: 시뮬레이션 / 모의 브로커

> 이번 거래는 시스템 장애가 아니라 진입/청산 정책 조합에 따른 손실 거래로 보는 것이 타당하다. 진입은 기준값에 걸친 경계선 진입이었고, 보유 중 고점 대비 하락폭이 커지며 peak drawdown 기준으로 청산됐다.

### 0.2 왜 이렇게 됐나

- 000660은 스캐너 2위 후보였고, 1순위 후보가 모니터 단계에서 막힌 뒤 차순위 재평가로 진입했다.
- 진입은 VWAP 재회복과 돌파 조건으로 성립했다.
- 진입 신뢰도는 0.55로 기준 0.55와 동일했다.
- 보유 중 고점 1,319,000원을 기록했으나, 청산가는 1,315,000원이었다.
- 청산은 고점 대비 하락폭 기준으로 실행됐다.
- 메모리 적용 결과 breakout buffer는 더 보수화됐고, peak_drawdown 기준은 더 타이트해졌다.

### 0.3 잘한 점

- 브로커 매수가/매도가와 키움 당일 실현손익이 연결되어 Truth Surface가 안정적이다.
- 진입 run과 청산 run이 연결되어 라이프사이클 추적이 가능하다.
- Supervisor 승인, Executor 실행, Broker 결과가 분리되어 기록됐다.
- 전략가, 스캐너, 모니터의 역할 경계가 유지됐다.

### 0.4 잘못된 점 / 취약점

- 당일 닫힌 거래 기준 성과가 2승 / 6패 / 평균 -0.40%로 부진했다.
- Monitor 단독 경로와 차순위 재평가 경로가 반복됐다.
- 진입은 더 보수적으로, 청산은 더 민감하게 작동해 손익 구조가 불리해졌다.
- 보유 구간의 중간 모니터 문맥이 부족해 청산 전 변화 분석이 제한된다.

### 0.5 개선 우선순위

1. Exit 정책 점검: peak_drawdown activation, confirm, min-hold 우회 여부 확인
2. Entry 정책 점검: 신뢰도 기준에 걸친 경계선 진입 반복 여부 확인
3. Scanner-Monitor 정합성 점검: 상위 후보가 반복 탈락하고 차순위 진입하는 구조가 성과를 악화시키는지 확인
4. 리포트 데이터 보존 개선: 보유 구간 모니터 스냅샷과 동일 일자 리포터 분석 연결 강화

### 0.6 상세 확인 위치

- 가격/손익 확정값: `2. Truth Surface`
- 메모리와 정책 변화: `3. 전략 / 메모리 / 정책 영향`
- 종목 선정 과정: `5. 스캐너 / 종목 선정`
- 진입/보유/청산 근거: `6. 거래 라이프사이클`
- 당일 반복 패턴: `8. 당일 패턴과 결과 평가`
- 원본 로그 경로: `10. 근거 출처 / Provenance`

---

## 5. Codex 작업 지시

Codex는 다음 작업을 수행한다.

### 5.1 출력 구조 변경

현재 `ai_trade_report.md` 생성 로직을 찾아 위 목표 구조에 맞게 섹션 순서를 재배치한다.

필수 조건:

- `운영 요약`을 최상단에 추가한다.
- 기존 정보는 삭제하지 않는다.
- 중복 문장은 합친다.
- 세부 근거는 아래 섹션으로 이동한다.
- 기존 provenance, run_id, truth source는 반드시 유지한다.

### 5.2 Operator Summary 생성

다음 필드를 우선적으로 조합해 운영 요약을 만든다.

- realized_pnl / realized_pnl_pct
- lifecycle_status
- execution_mode
- entry_reason
- entry_confidence / threshold
- exit_reason / actual_exit_trigger
- scanner_rank / scanner_score
- memory policy deltas
- same-day closed trade summary
- repeated path patterns
- reporter recommendations

### 5.3 중복 제거 규칙

다음 내용은 한 번만 대표 섹션에 표시한다.

- 브로커 매수가/매도가/손익
- 시장 상태 / 글로벌 감성 / VIX
- 전략가 역할 경계
- 스캐너 선정 이유
- 청산 사유
- 참조 경로

다른 섹션에서는 필요한 경우 “상세는 n번 섹션 참고” 형태로 연결한다.

### 5.4 부자연스러운 문구 정규화

다음 표현을 정리한다.

- `시장 시장 상태` → `시장 상태`
- `진입 유지 판단이며 ... 매도` → 청산 완료 상태와 모순 없게 수정
- `스캐너 최고 순위 후보` → 실제 순위/점수와 일치하도록 수정
- `닫힌 거래 0건`과 `닫힌 거래 9건`처럼 시점이 다른 값은 각각 `전략가 입력 시점` / `사후 복원 시점`으로 분리

### 5.5 테스트 / 검증

가능하면 아래 테스트를 추가하거나 기존 테스트를 보강한다.

- 운영 요약 섹션이 최상단에 존재하는지
- Truth Surface 정보가 누락되지 않는지
- run_id / provenance가 유지되는지
- entry / exit / memory / same-day pattern 정보가 모두 포함되는지
- 중복 섹션이 과도하게 반복되지 않는지
- 샘플 리포트에서 부자연스러운 문구가 제거되는지

---

## 6. 완료 기준

작업 완료 기준은 다음과 같다.

1. 운영자가 리포트 상단 1분만 읽어도 다음을 알 수 있어야 한다.
   - 이번 거래가 이익인지 손실인지
   - 왜 그렇게 됐는지
   - 시스템이 잘한 점
   - 시스템이 잘못한 점
   - 무엇부터 개선해야 하는지

2. 세부 분석이 필요한 경우 아래 섹션에서 기존 수준의 근거를 모두 확인할 수 있어야 한다.

3. 리포트가 전략가 입력용과 혼동되지 않아야 한다.

4. 기존 canonical artifact / provenance / truth source 기반 추적 가능성이 유지되어야 한다.
