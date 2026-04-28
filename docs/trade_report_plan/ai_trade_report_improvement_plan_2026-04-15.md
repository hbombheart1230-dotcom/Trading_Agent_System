# AI Trade Report Improvement Plan (2026-04-15)

## 목표

`ai_trade_report.md`를 운영자용 진단 문서로 정상화한다.

- 팩트는 그대로 유지한다.
- LLM은 숫자를 만들지 않고 해석과 평가를 맡는다.
- 2026-04-25 기준 batch 재생성의 기본값은 no-LLM deterministic report다.
- 위 no-LLM 기본값은 batch/manual 재생성에만 적용한다. live closed-trade first-write는 `--trade-report-ai`로 report LLM을 호출한다.
- batch/manual 재생성에서 LLM은 `--with-llm`을 명시한 경우에만 optional operator-facing narrative layer로 사용한다.
- LLM 출력은 memory source가 아니며, memory는 deterministic artifact와 explicit trace에서만 계산한다.
- 현재 artifact만으로 가능한 개선을 우선 수행한다.
- 상위 런타임이나 trading logic은 이번 단계에서 건드리지 않는다.

## 현재 문제 정의

현재 `ai_trade_report.md`는 다음 문제가 섞여 있다.

- 시장 뉴스와 종목 뉴스가 같은 섹션에 뒤섞인다.
- `전략가 입력`은 보이지만 `전략가 해석`과 `스캐너 반영 결과`가 약하다.
- deterministic bullet과 LLM 문장이 뒤섞여서 운영자 입장에서 인과가 잘 안 읽힌다.
- 메모리 표기가 전략가 입력 시점, 스캐너 적용 시점, 모니터 적용 시점, 최신 commander 상태를 분리하지 못하면 `active_layers=[]`와 실제 `monitor applied`가 같은 거래에서 충돌처럼 보인다.
- salvage 경로에서는 상위 섹션만 LLM이 쓰고 나머지는 fallback 조합이 강하게 드러난다.
- 영문/한글 혼합과 중복 문구 때문에 읽기 피로가 높다.

## 현재 artifact로 가능한 범위

현 단계에서 대부분은 이미 저장된 artifact로 해결 가능하다.

### 가능한 것

- 시장 환경을 지수, VIX, 감성, 뉴스, 테마 기준으로 재구성
- 전략가 입력을 바탕으로 `해석`과 `플레이북`을 문장화
- 스캐너 선택 근거를 점수와 기여 항목 중심으로 정리
- 진입, 보유, 청산, 실행 결과를 운영자용 평가 문장으로 변환
- 결과 평가에서 `scanner / entry / hold / exit` 책임 축 분류

### 바로는 어려운 것

- headline 단위로 스캐너 점수 반영률을 정확히 역추적
- 전략가 내부 reasoning chain을 완전 재현
- hold 중 미세 신호 변화의 상세 causal chain 완전 복원

즉 이번 단계는 "때려 고치는 단계"가 아니라 "이미 있는 evidence를 좋은 운영자용 보고서로 재배열하는 단계"다.

## 설계 원칙

### 1. deterministic layer

이 레이어는 사실과 provenance를 책임진다.

- 숫자
- 경로
- source
- canonical artifact link
- lifecycle facts
- scanner score and driver values
- monitor and execution facts

### 2. LLM layer

이 레이어는 평가와 인과를 책임진다.

- 왜 이 종목을 골랐는가
- 왜 여기서 들어갔는가
- 왜 계속 들고 있었는가
- 왜 그 시점에 나갔는가
- 이번 거래의 실패 축은 어디인가

### 3. 금지 사항

- 없는 숫자 생성
- 없는 뉴스 생성
- runtime trading logic 변경
- report/trades schema breaking change
- provenance 삭제

## 개선 단계

### Phase 1. Section contract 정리

대상: `market_context_at_entry`, `strategist summary`, `why_this_symbol_was_chosen`, `scanner_filters`, `reporter_evaluation`

핵심 작업:

- `시장 환경 요약`을 headline dump가 아니라 5개 시장 판단 축으로 재구성
- `전략가 요약`에 입력 나열이 아니라 `입력 -> 해석 -> scanner_handoff / monitor_handoff` 추가
- `실제로 적용된 결정론적 메모리 bias`는 `전략가 입력 시점 -> 스캐너 적용 시점 -> 모니터 적용 시점 -> 최신 커맨더 상태` 순서로 분리
- `종목 선택`은 스캐너 섹션에서 점수, 필터, tie-break 기준으로 설명
- `선택된 종목 상세 분석`에서 점수와 우위 근거를 읽기 쉽게 정리
- `스캐너 후보 비교`에서 상대 비교와 통과/약점 축을 명확하게 분리
- `결과 평가`에 실패 책임 축을 명시

완료 기준:

- 운영자가 각 섹션에서 "그래서"를 읽을 수 있어야 한다.

### Phase 2. LLM vs fallback 역할 정리

대상: `libs/reporting/trade_report_ai.py`

핵심 작업:

- LLM이 써야 할 문장과 deterministic이 채워야 할 숫자를 분리
- salvage 시에도 섹션 구조가 무너지지 않게 보정
- 영문 조각과 중복 문장을 줄임

완료 기준:

- salvage 상태에서도 문장이 운영자용으로 읽혀야 한다.

### Phase 3. 전략가-스캐너 연결 강화

대상: market/strategist/scanner surface

핵심 작업:

- 주요 시장 뉴스 -> 전략가 해석 -> scanner contribution의 연결 문장 추가
- `news_scanner_contribution`를 숫자와 해석 모두에서 활용
- headline 나열 대신 "이 뉴스가 어떤 축을 강화했는가"를 보여줌

완료 기준:

- `전략가 요약`만 읽어도 어떤 전략 프레임이 스캐너와 모니터에 전달됐는지 설명 가능해야 한다.
- 왜 000660이 최종 선택됐는지는 스캐너 섹션만 읽어도 설명 가능해야 한다.

### Phase 4. 평가 축 명확화

대상: `reporter_evaluation`, `errors_weaknesses_improvement_points`

핵심 작업:

- 거래 실패 축을 `scanner quality`, `entry timing`, `hold management`, `exit logic`, `execution quality`로 분류
- 다음 액션 포인트를 한 줄로 제시

완료 기준:

- 운영자가 "무엇을 다음에 손봐야 하는가"를 리포트에서 바로 읽을 수 있어야 한다.

## 예상 수정 범위

핵심 파일은 제한적이다.

- `libs/reporting/trade_report_ai.py`
- `tests/test_trade_report_ai.py`

필요 시 참고 파일:

- `reports/trades/2026-04-15/TRD_20260415_000660_01/reports/ai_trade_report.md`
- `reports/trades/2026-04-15/TRD_20260415_000660_01/reports/ai_trade_report_llm_response.json`

이번 단계에서는 상위 runtime, graph node, execution logic을 건드리지 않는 것을 원칙으로 한다.

## 구현 순서

1. 문안 목표와 section contract를 먼저 고정
2. `trade_report_ai.py`의 prompt와 section assembly를 수정
3. fallback 문장 품질 보정
4. targeted regression test 추가
5. 대표 trade 1건 재생성 후 품질 검토

## 검증 방법

대표 검증 trade:

- `TRD_20260415_000660_01`
- live phase-split 검증 trade:
  - `TRD_20260427_005930_05`

검증 포인트:

- `시장 환경 요약`에 시장 판단 축 5개가 보이는지
- `전략가 요약`에서 입력과 해석과 scanner connection이 분리되는지
- `실제로 적용된 결정론적 메모리 bias`에서 전략가 입력 시점, 스캐너 적용 시점, 모니터 적용 시점, 최신 커맨더 상태가 각각 한 줄로 보이는지
- 스캐너 시점이 `disabled`여도 모니터 시점의 `entry/exit applied`가 별도 phase로 보이는지
- 최신 commander 상태가 전략가 입력 시점과 다르면 `시점 차이` 안내가 붙는지
- `선택된 종목 상세 분석`에서 점수 우위와 비교 대상이 읽히는지
- `스캐너 후보 비교`에서 후보 간 상대 우위와 약한 축이 읽히는지
- `결과 평가`가 단순 사실 반복이 아니라 책임 분류를 하는지
- salvage 상태에서도 읽기 품질이 유지되는지

## 성공 기준

- 운영자가 `왜 골랐고`, `왜 들어갔고`, `왜 나갔는지`를 리포트 한 장으로 이해할 수 있다.
- 운영자가 메모리 상태를 읽을 때 `프롬프트에는 없었음`, `스캐너에는 미적용`, `모니터에는 적용`, `최신 commander는 활성` 같은 phase 차이를 오해하지 않는다.
- 숫자와 provenance는 기존 artifact와 충돌하지 않는다.
- batch/manual 재생성에서 LLM은 선택적 사후 해설자로 기능하고, deterministic layer는 사실 수집자이자 기본 리포트 생성자로 남는다.
- live closed-trade first-write에서는 LLM report가 기본 산출물이어야 한다.
- 상위 런타임을 수정하지 않고도 체감 품질이 분명히 좋아진다.

## 이번 단계에서 하지 않을 것

- trading strategy tuning
- monitor entry/exit semantics 변경
- scanner ranking policy 변경
- lifecycle schema 변경
- report/trades directory 구조 변경
- headline 단위 attribution 완전 추적 구현

## 시작 기준

구현은 이 문서를 기준으로 진행한다.

- 기준 예시: `docs/trade_report_plan/ai_trade_report_target_example_2026-04-15.md`
- 기준 계획: `docs/trade_report_plan/ai_trade_report_improvement_plan_2026-04-15.md`
