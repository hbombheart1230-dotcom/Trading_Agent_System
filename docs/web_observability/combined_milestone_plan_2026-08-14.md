# 운영·포트폴리오 UI 통합 마일스톤

작성일: 2026-08-14

구현 시 최우선 하드 경계는
`docs/web_observability/isolation_and_modularity_contract.md`를 따른다.
Trading Runtime 격리와 기능 단위 모듈화 gate를 통과하지 못하면 해당
마일스톤은 완료로 처리하지 않는다.

## 1. 제품 목표

이 UI의 주 목적은 평가 과정을 보여주는 것이 아니다.

목표는 기존 시스템이 만든 데이터를 이용해 다음을 한눈에 판단할 수
있는 read-only 운영 제품을 만드는 것이다.

* 오늘과 누적 수익이 어떤가
* 승률, 손익비, 비용, 낙폭이 어떻게 변하고 있는가
* 어떤 종목·테마·전략·시간대·보유기간에서 성과가 갈렸는가
* 어떤 후보를 샀고, 왜 샀으며, 왜 팔았는가
* 사지 않은 후보 중 실제로 좋은 기회가 있었는가
* 매매가 없었던 이유가 시장 때문인지 시스템 차단 때문인지
* 데이터 누락, 브로커 불일치, 종목 오염 같은 이상이 있는가
* 전략가·스캐너·모니터·지휘관의 판단 흐름이 앞뒤가 맞는가

포트폴리오 관점에서는 복잡한 내부 Q 번호보다, 시스템이 시장을 읽고
후보를 고르고 위험을 통제하고 결과를 복기하는 흐름이 명료하게 보여야
한다.

## 2. 평가 데이터의 역할

Q9~Q18과 현재 shadow 연구는 UI 콘텐츠 그 자체가 아니다. 화면에서
사용할 데이터와 진단 지표를 검증해 온 내부 근거다.

따라서 UI에는 다음을 전면 노출하지 않는다.

* Q13/Q14 Validation 진행률
* GO / NO-GO 판정 과정
* Q9~Q18 번호별 상세 결과
* promotion 절차와 내부 stopping rule
* 계약 hash와 연구용 schema 세부 정보

대신 그 데이터로 만든 사용자 관점의 결과를 보여준다.

예:

* `Scanner Ranking Failure` -> `상위 후보 적중도`와 `놓친 기회`
* `Candidate Filtering` -> `후보 → 승인 → 진입 전환 퍼널`
* `Exit Horizon` -> `계획 보유시간 대비 실제 보유시간`과 `청산 후 경로`
* Q10~Q12 -> `단순 기준선 대비 시스템 성과`
* opening Rank-1 연구 -> `장초반 후보의 시간대별 수익 경로`
* memory integrity -> `메모리 일치율`, `의사결정 반영 여부`, `오염 경고`

평가가 끝난 뒤에도 화면이 유효한 이유는 Q 결과를 보여주기 때문이
아니라, 동일한 운영 지표와 거래 데이터를 계속 누적해서 보여주기
때문이다.

## 3. 화면 정보 구조

### 3.1 Overview

첫 화면은 운영자가 10초 안에 상태를 파악하는 요약 화면이다.

상단 고정 정보:

* `READ ONLY`
* 모의/실계좌 구분
* 장 상태
* 런타임 상태와 마지막 갱신 시각
* 데이터 신뢰 상태

핵심 KPI:

* 당일 실현손익
* 당일 미실현손익
* 당일 순수익률
* 총 거래비용과 비용 잠식률
* 거래 수 / 승 / 패 / 보합
* 승률
* 평균 수익 / 평균 손실
* Profit Factor
* 최대 낙폭
* 현재 보유 종목과 주문 상태

기간 선택:

* 오늘
* 최근 5거래일
* 최근 20거래일
* 월간
* 전체

주요 시각화:

* 누적 손익 곡선
* 일별 순수익 막대
* 승/패 및 비용 구성
* 후보 → 승인 → 진입 → 청산 퍼널
* 오늘 시장 상태와 매매 시점 오버레이
* 운영 이상 징후 요약

### 3.2 Performance

성과를 여러 축으로 빠르게 비교하는 화면이다.

필수 지표:

* 총손익, 순손익, 수익률
* gross / broker net / live-equivalent net 분리
* 수수료, 세금, 슬리피지 분리
* 승률, 기대값, Profit Factor, MDD
* 평균/중앙 보유시간
* 평균 MFE / MAE
* 수익 반납률

분해 차원:

* 종목
* 테마
* market playbook
* tactical strategy / subtype
* Scanner rank와 candidate source
* 진입 패턴과 청산 사유
* strategy horizon
* 시간대
* 시장 regime
* 첫 진입 / 동일 종목 재진입

표본 수와 데이터 coverage는 모든 집계 옆에 표시한다. 표본 부족을 0점
또는 실패로 표현하지 않는다.

### 3.3 Trades

거래 목록과 개별 거래의 전체 의사결정 계보를 보여준다.

목록:

* 종목코드와 정확한 종목명
* 해당 거래에서 사용된 테마
* 매수/매도 시각
* 보유시간
* 수량과 가격
* gross/net 손익
* 비용
* 전략, horizon, Scanner rank
* 진입/청산 사유

상세:

* 시장 → 전략가 1차 → Scanner → 전략가 2차 → 지휘관 정책 → Monitor
  진입 → 보유 중 3차 → 4차 carry 검토 → 청산 타임라인
* Scanner 원점수와 점수 성분
* 선택 후보와 runner-up 비교
* 진입 당시 차트 상태
* MFE/MAE와 가격 경로
* 매도 후 +5/+15/+30/+60분 및 장기 horizon 추적
* broker truth / lifecycle / report 일치 여부
* AI 거래 요약과 상세 리포트 링크

### 3.4 Opportunities

실제 거래가 적어도 시스템의 기회 포착 능력을 볼 수 있는 화면이다.

* 시간대별 Scanner 후보 수
* Top1/Top3/Top5/Top10 forward 성과
* 후보 source별 성과
* 승인, 차단, NOOP 사유 분포
* 차단 후보의 이후 +5/+15/+30/+60/EOD 경로
* 장초반 Rank-1 결과
* fresh change activation
* latent reactivation
* 동일 종목 재진입 sequence
* 놓친 상승과 피한 손실을 분리한 opportunity cost

여기서 Q9/Q11/offline-alpha라는 내부 이름은 보조 provenance로만 남기고,
화면 제목은 업무 의미로 표시한다.

### 3.5 Strategies

전략의 다양성과 성과를 비교한다.

* playbook / tactic / subtype 분포
* 전략별 승률, 기대값, Profit Factor, MDD
* 전략별 추천 horizon과 실제 보유시간
* 전략과 실제 Rank-1 setup의 match / compatible / mismatch
* 테마 선호와 실제 종목 테마 정합성
* LLM 요청 전략과 최종 전략 차이
* 메모리 사용/미사용과 이후 결과

이 화면은 LLM을 평가하는 연구 화면이 아니라, 현재 시스템이 어떤 전략을
얼마나 사용했고 결과가 어땠는지 보여주는 운영 분석 화면이다.

### 3.6 Market

매매 결과를 시장 맥락과 함께 본다.

* KOSPI, KOSDAQ, KOSPI200
* KRX 야간선물
* S&P 500, NASDAQ
* 원달러, DXY
* VIX와 글로벌 감성
* 금리
* 시장 breadth
* 뉴스 감성 및 주요 테마
* market regime rail
* 지수 흐름 위 매수/매도/NOOP 시점

시장 데이터가 없거나 stale이면 차트를 숨기지 않고 coverage와 마지막
수집 시각을 명확히 표시한다.

### 3.7 Reports

사람이 읽는 결과물을 모은다.

* 일간/주간/월간 운영 요약
* 개별 거래 AI summary
* 종목별 summary
* 누적 성과 리포트
* 선택한 기간의 정량 분석 리포트

Markdown은 안전하게 렌더링하되 raw HTML을 실행하지 않는다. 원본 JSON은
내부 운영 모드에서만 보조 보기로 제공한다.

### 3.8 Data Quality

개발자 도구가 아니라 운영 신뢰성 화면이다.

* broker / lifecycle / report 거래 수 일치
* 실현손익과 수익률 일치
* 종목코드/종목명/테마 일치
* 누락 거래와 중복 거래
* stale artifact
* forward 관측 coverage
* 메모리 symbol mismatch
* closeout 실패
* 런타임 비정상 종료

상세 run/event/log는 이 화면의 고급 진단 drawer 안에 둔다. 기본 메뉴에
`Events`를 전면 배치하지 않는다.

## 4. Q9~Q18 데이터 활용 매핑

| 내부 프로그램 | 사용자 화면에서 활용할 데이터 | 화면에 표시하지 않을 것 |
| --- | --- | --- |
| Q9 | 후보 퍼널, P/A/B/C 비교, Top-K forward, source 성과 | Q9 진행률과 내부 gate |
| Q10 | 삼성전자/하이닉스 단순 기준선 비교 | Q10 프로그램 번호 |
| Q11 | 장초반 기회, 반전, 가상 probe 경로 | Q11 계약 상태 |
| Q12 | BTC-우리기술투자 연동 비교 | Q12 평가 절차 |
| Q13 | 단계별 정합성·타이밍·horizon 이상 탐지 | 0~100 점수 자체를 메인 KPI로 사용 |
| Q14 | 후보 순위/필터/전략가 개입/증거누락 원인 | promotion 판정 과정 |
| Q15 | runner-up 전환 현황과 차단 영향 | Q15 패치 평가 이력 |
| Q16 | 방향성 evidence와 비용 통과/차단 현황 | Q16 day 번호 |
| Q17 | 계획 horizon 대비 실제 보유·청산 정합성 | contract repair 내부 상태 |
| Q18 | post-reclaim setup의 shadow 성과 | 종료된 승격 검토 과정 |

Q15/Q16과 same-symbol loss reentry control처럼 실제 적용된 정책은 거래
상세의 `적용된 정책` 근거로 표시할 수 있다. Dashboard에는 정책 이름을
나열하지 않고 그 결과인 차단 수, 피한 손실, 놓친 기회를 보여준다.

## 5. 현재 연구 데이터 활용

현재 연구는 UI 구현을 막지 않는다. 기존 산출물을 read-only로 연결하며,
연구 종료 후에도 같은 도메인 지표로 계속 누적한다.

| 현재 수집 | 운영 화면의 최종 형태 |
| --- | --- |
| Fixed Rank-1 candidates | 장초반 후보 특성별 forward 성과 |
| Fresh Change Activation | 변화율 활성화 후보와 비활성 후보 비교 |
| Latent Reactivation | 이전 후보가 새 신호에서 재점화된 경로 |
| Same-Symbol Sequence | 첫 거래·재진입·누적손익·수익 반납 |
| Strategy/Setup Alignment | 전략과 실제 후보 setup 조합별 성과 |
| Memory Integrity | 메모리 일치율, 적용률, 성과 연결 coverage |

연구용 sample gate는 UI에 진행률로 표시하지 않는다. 단, 분석 결과의 오해를
막기 위해 각 차트에 `N`, coverage, 기간, 비용 기준은 항상 표시한다.

## 6. Read Model과 API 경계

신규 API는 Q 번호별 reader보다 사용자 도메인별 reader를 우선한다.

범용성 원칙:

* UI는 Kiwoom 응답 필드명을 직접 사용하지 않는다.
* UI는 Q9/Q13 같은 평가 schema를 직접 해석하지 않는다.
* 공통 view model은 `Trade`, `Portfolio`, `PerformanceSeries`,
  `Opportunity`, `StrategyBreakdown`, `MarketSnapshot`, `DataQualityIssue`로
  고정한다.
* Kiwoom, operator summary, Q9, offline alpha는 각각 source adapter가 공통
  view model로 변환한다.
* 향후 broker나 평가 모듈이 바뀌어도 adapter만 추가하고 UI는 유지한다.

제안 모듈:

```text
apps/api/services/
  overview_reader.py
  portfolio_reader.py
  performance_reader.py
  trade_reader.py
  opportunity_reader.py
  strategy_reader.py
  market_reader.py
  report_reader.py
  data_quality_reader.py
  system_reader.py

apps/api/adapters/
  kiwoom/
  operator_summary/
  trade_reports/
  evaluation/
  offline_alpha/
  market/
```

제안 API:

```text
GET /health/live
GET /health/ready
GET /api/v1/overview
GET /api/v1/portfolio
GET /api/v1/performance/summary
GET /api/v1/performance/series
GET /api/v1/performance/breakdown
GET /api/v1/trades
GET /api/v1/trades/{trade_id}
GET /api/v1/opportunities/funnel
GET /api/v1/opportunities/outcomes
GET /api/v1/strategies/performance
GET /api/v1/market/snapshot
GET /api/v1/market/series
GET /api/v1/reports
GET /api/v1/reports/{report_id}
GET /api/v1/data-quality
GET /api/v1/system/status
```

Q9~Q18 원본 조회는 내부 provenance 또는 report detail로 충분하다. 신규
공개 API의 최상위 구조를 평가 단계에 종속시키지 않는다.

## 7. 현재 데이터 가용성

| 화면 데이터 | 현재 근거 | 상태 | 구현 시 주의점 |
| --- | --- | --- | --- |
| 당일 거래/승패/수익률 | `reports/operator_summary/daily/*/daily_summary.json` | 사용 가능 | 무거래와 미확정 손익 구분 |
| 주문/체결/계좌 truth | `data/logs/kiwoom_account_snapshots/*` | 사용 가능 | raw 계좌/주문 식별자 비노출 |
| 누적 일별 성과 | `reports/performance/*/summary.json` 및 operator summaries | 재집계 필요 | broker truth와 drift 검사 필요 |
| 전략/패턴/horizon | daily summary, performance memory, trade reports | 사용 가능 | 표본 수와 비용 기준 동반 |
| 개별 거래 계보 | lifecycle bundle, AI trade report/summary | 사용 가능 | canonical trade ID로 연결 |
| 후보/차단/forward | Q9 decision windows, Q8/Q13/Q14 reports | 사용 가능 | 82MB 파일 request-time 전체 scan 금지 |
| 장초반/latent/reentry | offline-alpha artifacts | 사용 가능 | 연구 이름 대신 업무 개념으로 표시 |
| 시장/지수/감성 | `data/logs/macro_indicators/*` | 사용 가능 | stale/coverage 표시 |
| 데이터 정합성 | artifact inventory, broker reconciliation, closeout | 사용 가능 | 운영 alert로 정규화 필요 |
| 공개 포트폴리오 snapshot | 현재 없음 | 신규 필요 | sanitized export 또는 공개 profile 필요 |

현재 데이터만으로 주요 화면은 구성 가능하다. 새 트레이딩 계측을 먼저
추가할 필요는 없다. 다만 누적 equity curve, 비용 기준 통일, 거래 계보
index, 후보 대용량 index, 공개용 redaction은 신규 read-only 계층에서
정규화해야 한다.

## 8. 데이터 권위 원칙

* 체결·주문·보유·실현손익은 Kiwoom broker truth를 우선한다.
* 거래 계보는 lifecycle bundle과 canonical trade read model을 사용한다.
* 사람이 보는 설명은 AI summary를 사용하되 수치 권위로 사용하지 않는다.
* 전략/후보/차단 분석은 Q9 decision window와 evaluation artifacts를 사용한다.
* 시장 맥락은 `data/logs/macro_indicators`를 사용한다.
* gross, mock broker net, live-equivalent net을 절대 섞지 않는다.
* 값이 없으면 0으로 만들지 않고 `UNAVAILABLE` 또는 `INSUFFICIENT_DATA`로
  표시한다.
* 모든 집계는 기간, 표본 수, coverage, generated_at을 함께 반환한다.

## 9. 구현 마일스톤

### M0 - 제품 계약과 데이터 카탈로그

작업:

* 화면별 KPI와 용어 확정
* Q9~Q18 및 현재 연구를 사용자 도메인에 매핑
* broker/report/evaluation/market 권위 source map 작성
* 수익률·비용·승률 산식 계약 확정
* 내부 운영 모드와 포트폴리오 공개 모드 경계 확정

완료 기준:

* 같은 지표가 화면마다 다르게 계산되지 않는다.
* Q 번호가 사용자 정보 구조를 지배하지 않는다.

예상 작업 블록: 1

### M1 - Read-only API Foundation

작업:

* 독립 `apps/api` skeleton
* config, health, 공통 response, read-only/import isolation
* 안전한 파일 인덱스와 기간 필터
* 대용량 JSONL bounded reader

완료 기준:

* Trading Core import 0
* GET 외 method 0
* filesystem write 0
* path traversal, malformed JSON, stale source 테스트 통과

예상 작업 블록: 1~2

### M2 - Overview, Portfolio, Performance API

작업:

* broker-authoritative 당일/누적 KPI
* 기간별 equity/PnL series
* gross/net/cost decomposition
* 종목·테마·전략·horizon·시간대 breakdown
* 현재 보유/주문 read model

완료 기준:

* 대표 거래일 fixture에서 기존 report 수치와 일치
* 무거래일과 미확정 손익을 정확히 구분

예상 작업 블록: 2

### M3 - Trades and Reports API

작업:

* 거래 목록/검색/필터
* 거래 상세 timeline과 provenance
* MFE/MAE, post-exit, horizon 경로
* Markdown/JSON report 안전 조회

완료 기준:

* 한 거래를 UI 데이터만으로 재구성 가능
* 종목명/테마/손익 truth 오염 방지 테스트 통과

예상 작업 블록: 1~2

### M4 - Opportunities, Strategies, Market API

작업:

* 후보 전환 퍼널과 blocker 분석
* Top-K 및 미진입 forward outcome
* playbook/tactic/setup/horizon 성과
* 현재 offline-alpha와 memory 결과의 도메인 adapter
* 시장 지수, breadth, 감성, regime timeline

완료 기준:

* 평가 프로그램명을 몰라도 기회 포착과 전략 성과를 해석할 수 있다.
* 표본과 coverage가 없는 분석은 성과처럼 표시되지 않는다.

예상 작업 블록: 2~3

### M5 - Web UI MVP

작업:

* Overview
* Performance
* Trades
* Opportunities
* Strategies
* Market
* Reports
* Data Quality

디자인 기준:

* 운영 도구답게 조밀하지만 복잡하지 않은 정보 구조
* 핵심 수치와 추세 우선
* 카드 남용 금지
* 표, 차트, 필터, 비교가 중심
* desktop 우선이되 mobile에서도 수치와 표가 깨지지 않음
* 긴 Q 번호·run ID·파일 경로는 기본 화면에서 숨김

완료 기준:

* 10초 내 오늘 상태 파악 가능
* 3번 이내 탐색으로 거래 원인과 원본 리포트 접근 가능
* Loading/Partial/Unavailable/No Data/Error 구분

예상 작업 블록: 3~4

### M6 - 이상 탐지와 포트폴리오 공개 모드

작업:

* 데이터 신뢰성 alert
* 비용 급증, 손실 반복, 과도한 단기청산, 기회 누락 등 운영 anomaly
* 계좌번호, 주문 ID, 절대 경로, raw prompt/log, credential 흔적 제거
* 공개용 고정 snapshot 또는 sanitized API profile
* 공개 화면에 `simulation/mock` 상태를 명확히 표시

완료 기준:

* 내부 운영 데이터가 공개 모드에서 유출되지 않는다.
* 공개 화면도 임의의 성과를 만들지 않고 동일한 집계 계약을 사용한다.

예상 작업 블록: 1~2

### M7 - Docker Compose

작업:

* 최소 API/Web images
* reports/logs read-only mount
* localhost 기본 노출
* non-root, read-only filesystem, credential 미포함

완료 기준:

* Compose smoke 통과
* container 내부 evidence 쓰기 실패 증명

예상 작업 블록: 1

### M8 - Kubernetes Local Overlay

작업:

* Kustomize base/local overlay
* Docker Desktop hostPath/PVC read-only mount
* probes, resource limits, port-forward
* Trading Runtime은 cluster 밖에 유지

완료 기준:

* manifest build와 pod probe 통과
* API/UI만 명령줄로 시작·중지·조회 가능

예상 작업 블록: 1~2

### M9 - 통합 검증과 마감

작업:

* API/UI/Compose/Kubernetes smoke
* 대표 거래일·무거래일·손상 데이터 fixture
* 전체 Git 변경 경계와 Trading Core 무변경 audit
* 사용법 및 데이터 해석 문서

완료 기준:

* 기존 런타임·평가·주문 로직 변경 0
* UI KPI와 원본 artifact 대조 통과
* 내부 운영 모드와 공개 모드 모두 재현 가능

예상 작업 블록: 1

## 10. 실행 순서와 예상 규모

고정 순서:

```text
M0 Data Contract
 -> M1 API Foundation
 -> M2 Performance
 -> M3 Trades/Reports
 -> M4 Opportunities/Strategies/Market
 -> M5 UI
 -> M6 Showcase/Anomaly
 -> M7 Docker
 -> M8 Kubernetes
 -> M9 Final Audit
```

총 예상 작업 블록은 13~18개다. API 계약과 데이터 정합성에 먼저 시간을
쓰고 UI는 그 뒤에 연결한다. UI부터 만들면 기존 Markdown/JSON마다 계산이
달라져 다시 뜯게 될 가능성이 높다.

현재 active 연구는 이 구현과 병행한다. 연구가 끝날 때까지 UI 개발을
기다릴 필요가 없고, 연구 종료로 UI 메뉴를 삭제할 필요도 없다. 새 데이터는
`Opportunities`, `Strategies`, `Trades`의 동일한 view model에 누적된다.

## 11. 현재 제약

현재 호스트에서 다음 도구는 확인되지 않았다.

* Node/npm
* Docker CLI
* kubectl

따라서 M0~M4의 설계와 Python API 작업은 가능하지만, M5의 실제 frontend
build 및 M7~M8 실증 전에는 해당 도구 준비가 필요하다.

## 12. 비목표

* 평가 진행 상황을 메인 제품으로 만들지 않는다.
* 개발자용 log viewer를 첫 화면으로 만들지 않는다.
* Q19 이후 번호를 추가하지 않는다.
* UI에서 주문, 승인, 설정, prompt, 전략을 변경하지 않는다.
* UI가 promotion 또는 매매 정책을 결정하지 않는다.
* Trading Core, Q9~Q18 산식, 현재 shadow 계약을 변경하지 않는다.
