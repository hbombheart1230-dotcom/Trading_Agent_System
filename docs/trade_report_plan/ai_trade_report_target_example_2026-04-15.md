# AI Trade Report Target Example (2026-04-15)

## 목적

이 문서는 `ai_trade_report.md`가 최종적으로 어떤 흐름과 문체로 읽혀야 하는지 보여주는 목표 예시다.

- 기준 trade: `TRD_20260415_000660_01`
- 기준 artifact:
  - `reports/trades/2026-04-15/TRD_20260415_000660_01/reports/ai_trade_report.md`
  - `reports/trades/2026-04-15/TRD_20260415_000660_01/reports/ai_trade_report.json`
  - `reports/trades/2026-04-15/TRD_20260415_000660_01/reports/ai_trade_report_llm_response.json`

리포트 본문은 운영자가 한 번에 읽고 `시장 판단 -> 전략가 해석 -> 스캐너 선택 -> 진입 -> 보유 -> 청산 -> 결과 평가`를 따라갈 수 있어야 한다. 작성 규칙과 검수 포인트는 본문 예시 뒤의 `작성 메모`에 따로 둔다.

## 본문 예시

### Truth Surface

이번 거래의 숫자 기준은 브로커 체결과 키움 당일 손익이다. 이 구간만 읽어도 매수가, 매도가, 확정 손익, 수수료/세금, truth source를 바로 확인할 수 있다.

- 브로커 매수가/매도가는 `1,160,000 / 1,162,000`원이다.
- 확정 손익은 `+8,400원 / +0.72%`다.
- 브로커 수수료/세금은 `8,480 / 2,436`원이다.
- 가격 기준은 `broker_fill`, 손익 기준은 `kiwoom.ka10077`이다.
- 모니터 관측가는 뒤쪽 청산/모니터 섹션에서 보조 근거로만 다룬다.

### 전략가 프롬프트에서 직접 확인된 메모리

전략가 호출 당시 프롬프트에는 전략 메모리와 당일 리포터 피드백이 직접 포함됐다. commander는 `daily` 레이어만 활성화했고, 우선순위는 `daily -> weekly -> monthly -> symbol`이었다.

- 전략 메모리 상태는 정상이며, 우세/취약 플레이북 모두 `defensive`로 기록됐다.
- 최근 실패 신호도 `playbook:defensive`에 집중됐다.
- 당일 리포터 피드백은 `status=ok / confidence=high`로 사용 가능했다.
- 읽기 모델은 최근 거래와 종목 패턴이 직접 확인된 범위만 사용했다.
- 이 값들은 전략가 입력 근거이며, 실제 수치 조정 여부는 아래 메모리 적용 결과에서 따로 확인한다.

### 거래 설명용 사후 복원 메모리

거래 설명을 위해 000660의 저장된 종목 메모리와 당일 리포터 피드백을 다시 읽었다. 이 내용은 전략가 원본 프롬프트를 옮긴 것이 아니라, 체결된 거래를 해석하기 위해 사후 복원한 문맥이다.

- 000660 종목 메모리는 persisted symbol read model에서 복원했다.
- 최근 closed trade 4건 기준 승률은 50%, 주요 playbook은 `defensive`였다.
- 당일 리포터 피드백은 same-day closed trade reports와 reporter analysis를 기준으로 다시 구성했다.
- runtime loader 기준으로 weekly/monthly packet 존재 여부와 commander policy 활성 상태도 함께 확인했다.

### 실제로 적용된 결정론적 메모리 bias

메모리 영향은 전략가 입력, 스캐너 적용, 모니터 적용, 최신 커맨더 상태로 나눠 읽는다. 중요한 것은 “메모리를 넣었다”가 아니라 실제 점수나 정책이 무엇이 달라졌는지다.

- 전략가 입력 시점: 활성 레이어는 `daily`, 우선순위는 `daily -> weekly -> monthly -> symbol`이었다.
- 스캐너 적용 시점: scanner memory bias는 `daily` 기준으로 계산됐고, source weight는 `top_value +0.10`, `top_change_rate -0.25`로 바뀌었다.
- 이번 거래 종목 000660에는 symbol memory 가점 `+0.015`가 반영됐다.
- 모니터 적용 시점: entry policy에 메모리 bias가 적용됐다.
- monitor entry delta는 `breakout_buffer_pct 0.002 -> 0.003`, `max_extended_from_vwap_pct 0.050 -> 0.045`였다.
- 운영 해석은 명확하다. 추격 진입은 더 보수적으로 막았고, VWAP 대비 과열 구간 허용 폭은 줄였다.

### 시장 환경 요약

시장 전체는 과열보다 안정 쪽에 가까웠다. VIX는 중립 이하였고, 미국 주요 지수는 강세였다. 국내에서는 코스피 강세 기대와 대형주 선호 흐름이 부각됐고, 반도체 대형주에 우호적인 맥락이 형성됐다.

- VIX는 18.36, 전일 대비 -3.97%로 급격한 위험회피 장세는 아니었다.
- S&P500 +1.18%, Nasdaq +1.96%, Dow +0.66%로 글로벌 위험선호가 유지됐다.
- 국내 대형주 선호와 수급 유입 뉴스는 리더 종목에 우호적인 배경이었다.
- SK하이닉스 실적/목표가 상향 뉴스는 반도체 센티먼트를 보강했다.
- 시장 판단은 방어 일변도보다 리더 종목 눌림목 또는 재돌파를 볼 수 있는 환경이었다.

### 전략가 요약

전략가는 시장을 중립 이상으로 해석했고, `broad_market_leaders` 프레임에서 `눌림목` 플레이북을 유지했다. 이 해석은 스캐너에는 대형주와 테마 정렬 종목을 우대하라는 가이드로, 모니터에는 확인형 진입과 방어적 청산 가이드로 전달됐다.

- 핵심 입력은 global_sentiment 0.081, VIX 18.36, 미국 지수 강세, 국내 대형주 강세 뉴스였다.
- 전략가는 급격한 위험회피 장세가 아니라고 판단했다.
- scanner handoff는 거래대금, 리더 종목, 테마 정렬 후보를 우선 보라는 방향이었다.
- monitor handoff는 추격 진입을 피하고 VWAP/거래량 확인을 요구하는 쪽이었다.
- 000660이 최종 후보가 된 이유는 전략가가 아니라 스캐너의 후보 점수와 필터 통과 결과에서 설명한다.

### 전략가 출력 근거

전략가 출력은 playbook, risk tone, news usage, memory usage, scanner handoff, monitor handoff를 나눠 남긴다. 리포터는 이 구조화된 출력을 그대로 소비하고, 전략가가 최종 종목을 골랐다고 재구성하지 않는다.

- strategy thesis: `broad_market_leaders` / `pullback` / 정상 위험 톤.
- memory usage: `daily` 레이어 중심, 우선순위 `daily -> weekly -> monthly -> symbol`.
- news usage: 시장 뉴스는 위험선호 확인, 종목 뉴스는 반도체 리더 후보 보강에 사용.
- scanner handoff: 대형 리더, 거래대금, 테마 정렬 후보 우대.
- monitor handoff: VWAP 회복과 거래량 확인 없이는 진입 보류.

### 선택된 종목 상세 분석

000660은 후보 4개 중 1위였다. 단순 뉴스 수혜주라서가 아니라 거래대금, 모멘텀, 추세, 테마 정렬이 동시에 맞아떨어진 결과다.

- 최종 점수는 1.286, 신뢰도는 0.73, 리스크 점수는 0.56이었다.
- 주요 점수 축은 momentum 0.209, trading_value 0.200, trend 0.184였다.
- 005930(1.223), 047040(1.201) 대비 종합 점수 우위가 있었다.
- 종목 선택 자체는 무리한 픽으로 보기 어렵고, 리더 종목 선별 로직과 대체로 일치했다.

### 스캐너 후보 비교

스캐너 후보 비교는 선택 종목을 반복 설명하지 않고, 상대 우위와 탈락 경로만 정리한다.

- 후보 순위는 000660(1.286), 005930(1.223), 047040(1.201) 순이었다.
- 000660은 거래대금, 모멘텀, 추세, 섹터/테마 정렬, 차트 피처 커버리지가 상대적으로 우세했다.
- 005930은 점수 차가 크지 않았지만 종합 점수에서 뒤졌다.
- 047040은 리스크 점수가 더 높아 최종 우선순위가 밀렸다.
- fallback trade라면 상위 후보가 모니터에서 막힌 이유와 차순위 후보가 실제 진입된 이유를 한 줄로 정리한다.

### 진입 상세 근거

진입은 `breakout_above_recent_high_with_vwap_structure_confirmation` 조건으로 실행됐다. 전략가는 눌림목 프레임을 유지했지만, 실제 엔트리는 돌파 확인형에 가까웠다.

- 적용 정책은 1분봉, breakout_lookback 4, volume_ratio_min 0.73이었다.
- 진입가는 1,160,000원이었다.
- 종목 선택 논리와 진입 방식이 충돌한 것은 아니지만, 눌림목 관점에서는 다소 늦은 확인 진입으로 읽힌다.
- 이 거래의 핵심 리스크는 종목 선정 실패보다 entry timing 품질 저하 가능성이다.

### 보유 경과

보유 시간은 1분 3초로 매우 짧았다. 모니터는 총 6회 실행됐고, 핵심 감시 축은 `peak_drawdown`이었다.

- peak price는 1,162,000원이었다.
- current/exit price는 1,162,000원이었다.
- peak_drawdown은 -1.16%였다.
- 진입 직후 기대한 방향 지속성이 약했고, 수익 구간을 충분히 만들기 전에 흔들림 관리 국면으로 넘어갔다.
- 보유 단계 실패라기보다 entry 직후 포지션 안정화 시간이 부족했던 거래에 가깝다.

### 청산 판단 근거

청산은 `peak_drawdown` 트리거로 발생했다. 고정 손절 3.00% 도달이 아니라 장중 고점 대비 되밀림 감시 축에서 먼저 청산됐다.

- canonical exit reason은 `peak_drawdown`이다.
- 유효 손절 기준은 3.00%, 목표 수익 기준은 3.42%였다.
- 절대 손절선이 깨진 거래가 아니라, 짧은 반등 후 탄력이 이어지지 못해 관리형 청산이 실행된 거래다.
- exit bug보다는 entry 이후 follow-through가 약했던 케이스로 읽는다.

### 결과 평가

이 거래는 시장 해석 실패보다 진입 품질 문제 가능성이 더 크다. 시장, 전략가, 스캐너 레이어는 비교적 일관됐지만, 실제 진입 후 1분 안에 `peak_drawdown` 청산이 발생했다.

- scanner quality: 양호
- strategist context: 양호
- entry timing: 재점검 필요
- hold evidence: 판단 제한적
- exit logic: 규칙상 정상 작동
- day-level reporter feedback은 당일 손실 누적, cached strategist 재사용 비중, guard blocker 집중 같은 구조적 패턴을 보조 근거로만 붙인다.

### 보완 사안

보유 구간 근거가 얇아 진입과 청산 사이의 모니터 문맥을 더 보존할 필요가 있다. 이미 same-day reporter가 연결된 거래라면 중복 follow-up 문구는 숨긴다.

- entry 직후 follow-through 확인 기준을 더 세분화한다.
- 모니터 progression은 청산 직전 값만이 아니라 보유 중 변화 흐름도 남긴다.
- partial trade artifact나 ghost trade는 `_health.json` 기준으로 따로 표시하고 정상 리포트와 섞지 않는다.

### 최종 운영 판단

현재 판단은 청산 완료다. 이 거래는 종목 선정 실패보다 진입 타이밍 부담이 더 컸고, 다음 복기 포인트는 peak drawdown 청산이 방어적으로 타당했는지와 과도한 노이즈 청산은 아니었는지다. 재진입은 쿨다운 이후 새 스캐너 확인이 있을 때만 검토한다.

## 작성 메모

- 팩트는 deterministic artifact에서 온다.
- live closed-trade first-write는 `--trade-report-ai` 경로를 유지하며 report LLM을 호출한다.
- batch/manual 재생성은 기본 no-LLM deterministic report이며, LLM narrative가 필요할 때만 `--with-llm`을 쓴다.
- LLM은 팩트를 바꾸지 않고 인과와 평가를 설명한다.
- LLM prose는 향후 memory source로 쓰지 않는다.
- `Truth Surface`는 브로커 truth를 요약하고, 모니터 관측값과 섞지 않는다.
- 메모리 설명은 `prompt-proven`, `reconstructed`, `deterministic applied bias` 세 층으로 나눈다.
- deterministic applied bias는 `전략가 입력 시점`, `스캐너 적용 시점`, `모니터 적용 시점`, `최신 커맨더 상태`로 나눈다.
- 전략가는 최종 종목 선정자가 아니다. 최종 종목 선택은 스캐너와 모니터 실행 경로 기준으로 설명한다.
- `선택된 종목 상세 분석`은 선택 종목 자체를, `스캐너 후보 비교`는 top 후보 간 차이와 fallback 경로를 설명한다.
- `결과 평가`는 당일 집계 dump가 아니라 이번 거래의 책임 축을 먼저 설명한다.
- `local_debug` 재생성본은 live 생성본을 덮어쓰지 않고 별도 산출물로 남긴다.
