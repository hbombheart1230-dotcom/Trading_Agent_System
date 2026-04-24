# AI Trade Report Target Example (2026-04-15)

## 목적

이 문서는 `ai_trade_report.md`의 목표 문체와 섹션 책임을 정의한다.

- 기준 trade: `TRD_20260415_000660_01`
- 기준 artifact:
  - `reports/trades/2026-04-15/TRD_20260415_000660_01/reports/ai_trade_report.md`
  - `reports/trades/2026-04-15/TRD_20260415_000660_01/reports/ai_trade_report.json`
  - `reports/trades/2026-04-15/TRD_20260415_000660_01/reports/ai_trade_report_llm_response.json`

이 문서는 "최종 목표 문안" 예시다. 숫자 truth, provenance, memory audit, deterministic bias 적용 결과는 실제 artifact를 기준으로 유지하고, 표현은 운영자가 한 번에 읽고 책임 구간을 분리해서 이해할 수 있는 수준까지 올리는 것을 목표로 한다.

## 작성 원칙

- 팩트는 deterministic artifact에서 온다.
- LLM은 팩트를 바꾸지 않고, 인과와 평가를 설명한다.
- `Truth Surface`는 브로커 truth를 요약하는 섹션이고, 모니터 관측값과 섞지 않는다.
- 메모리 설명은 세 층으로 나눈다.
  - `전략가 프롬프트에서 직접 확인된 메모리`
  - `거래 설명용 사후 복원 메모리`
  - `실제로 적용된 결정론적 메모리 bias`
- `시장 환경 -> 전략가 해석 -> 스캐너 선택 -> 진입 -> 보유 -> 청산 -> 결과 평가`의 책임을 분리한다.
- `결과 평가`는 당일 집계 dump가 아니라, 이번 거래의 잘된 점과 실패 지점을 먼저 평가하고 day-level reporter는 보조 근거로만 쓴다.
- live 생성본과 `local_debug` 재생성본은 같은 파일을 덮어쓰지 않는다.

## 목표 예시

### Truth Surface

이번 거래의 숫자 truth는 브로커 체결과 키움 당일 손익 기준으로 요약한다. 운영자는 이 섹션만 읽어도 매수가, 매도가, 실현손익, 수수료/세금, truth source를 바로 확인할 수 있어야 한다.

- 브로커 매수가/매도가는 `1,160,000 / 1,162,000`원이다.
- 확정 손익은 `+8,400원 / +0.72%`다.
- 브로커 수수료/세금은 `8,480 / 2,436`이다.
- 가격 truth 소스는 `broker_fill`이다.
- 손익 truth 소스는 `kiwoom.ka10077`이다.
- 모니터 관측값은 뒤 섹션에서 보조 설명으로만 사용하고, truth 설명과 섞지 않는다.

### 전략가 프롬프트에서 직접 확인된 메모리

이 섹션은 실제 strategist input에서 확인된 메모리만 적는다. traded symbol 기준 사후 복원 정보와 섞지 않는다.

- 전략가 프롬프트에는 전략 메모리와 당일 리포터 피드백이 직접 들어갔다.
- commander는 `daily`만 active layer로 넘겼고, priority는 `daily -> weekly -> monthly -> symbol`이었다.
- 전략 메모리 신호는 `best_playbooks=defensive`, `worst_playbooks=defensive`, `recent_failures=playbook:defensive`였다.
- 당일 리포터 피드백은 `status=ok / confidence=high`로 사용 가능했다.
- read model facts는 직접 확인된 recent trade와 symbol pattern이 있을 때만 `사용`으로 적고, 없으면 억지로 채우지 않는다.
- 전략가 출력은 `playbook=defensive`, `monitor_guidance=defensive_exit`, `scanner_bias=leader`로 끝났다.

### 거래 설명용 사후 복원 메모리

이 섹션은 traded symbol 기준 read model, same-day closed trade report fallback, runtime loader rebuild처럼 "전략가 prompt 밖에서 거래 설명용으로 복원한 메모리"를 적는다.

- 000660 종목 메모리는 persisted symbol read model에서 다시 읽었고, 최근 closed trade 4건 기준으로 승률 50%, 주요 playbook은 `defensive`였다.
- 당일 리포터 피드백은 same-day closed trade reports와 reporter analysis를 기준으로 다시 구성했다.
- runtime loader 기준 메모리 packet을 다시 읽어 weekly/monthly packet이 존재하는지, commander policy가 실제로 무엇을 활성화했는지 복원했다.
- 이 섹션은 raw strategist prompt dump가 아니라 trade-centric reconstruction임을 명시한다.

### 실제로 적용된 결정론적 메모리 bias

이 섹션은 commander가 실제로 scanner와 monitor에 적용한 delta를 보여준다. "메모리를 넣었다"가 아니라 "그래서 실제 값이 무엇이 달라졌는가"를 설명해야 한다.

- scanner memory bias는 `daily` layer 기준으로 계산됐다.
- scanner source weight delta는 `top_value +0.10`, `top_change_rate -0.25`였다.
- 이번 거래 종목 000660에는 symbol memory 추가 가점이 `+0.015` 반영됐다.
- monitor memory bias는 entry policy에 적용됐다.
- monitor entry delta는 `breakout_buffer_pct 0.002 -> 0.003`, `max_extended_from_vwap_pct 0.050 -> 0.045`였다.
- 해석은 숫자를 그대로 다시 읽지 말고, `추격 진입을 더 보수적으로 막았고 과열 구간 허용 폭을 줄였다`처럼 운영자 문장으로 붙인다.

### 시장 환경 요약

시장 전체는 과열보다는 안정에 가까웠다. VIX는 중립 이하였고 미국 주요 지수는 강세였다. 국내에서는 코스피 강세 기대와 대형주 선호 흐름이 부각됐고, 반도체 대형주에 우호적인 맥락이 형성됐다.

- 변동성 완화: VIX 18.36, 전일 대비 -3.97%로 급격한 위험회피 장세는 아니었다.
- 글로벌 위험선호: S&P500 +1.18%, Nasdaq +1.96%, Dow +0.66%로 미국 증시 분위기는 우호적이었다.
- 국내 대형주 선호: 코스피 강세 기대와 수급 유입 뉴스가 대형 리더 종목에 유리한 배경을 만들었다.
- 반도체 우호 재료: SK하이닉스 실적/목표가 상향 뉴스는 종목 단위 센티먼트 강화 요인으로 작동했다.
- 시장 해석: 방어보다 리더 종목 눌림목 또는 재돌파 시도를 볼 수 있는 환경이었다.

### 전략가 요약

전략가는 시장을 중립 이상으로 해석했고, `broad_market_leaders` 프레임에서 `눌림목` 플레이북을 유지했다. 이 해석은 스캐너에 대형주와 테마 정렬 종목 우대 형태로 전달됐고, 그 결과 000660이 상위 후보가 됐다.

- 핵심 입력: global_sentiment 0.081, VIX 18.36, 미국 지수 강세, 국내 대형주 강세 뉴스.
- 전략 해석: 급격한 위험회피 장세가 아니라 리더 종목 중심 접근이 가능한 환경으로 판단했다.
- 스캐너 반영: sentiment 기여 +0.018, theme_boost +0.067이 선택 점수에 반영됐다.
- 종목 연결: 000660은 `top_value + sector_theme` 조합으로 종합 점수 1.286을 받아 1위로 선택됐다.
- 해석 주의점: 시장과 종목 맥락은 우호적이었지만, 실제 진입 타이밍 품질은 별도로 검증해야 한다.

### 선택된 종목 상세 분석

000660은 후보 4개 중 1위였다. 단순 뉴스 수혜주라서가 아니라 거래대금, 모멘텀, 추세, 테마 정렬이 동시에 맞아떨어진 결과다.

- 최종 점수: 1.286
- 신뢰도: 0.73
- 리스크 점수: 0.56
- 주요 점수 축: momentum 0.209, trading_value 0.200, trend 0.184
- 비교 우위: 005930(1.223), 047040(1.201) 대비 점수 우위
- 해석: 종목 선택 자체는 무리한 픽으로 보기 어렵고, 리더 종목 선별 로직과 대체로 일치한다.

### 스캐너 후보 비교

이 섹션은 "왜 이 종목이 선택됐는지"를 상대 비교 관점에서 설명한다. 선택 종목 섹션과 같은 문장을 반복하지 않고, top2/top3와의 차이와 fallback 경로만 정리한다.

- 후보 비교 결과: 000660(1.286), 005930(1.223), 047040(1.201) 순으로 점수 우위가 확인됐다.
- 통과 축: 거래대금, 모멘텀, 추세, 섹터/테마 정렬, 차트 피처 커버리지가 상대적으로 우세했다.
- 약한 축: turnover/volume 계열은 압도적 우위가 아니었고, 일부 후보와의 격차는 크지 않았다.
- 차순위 비교: 005930은 점수 차가 작았지만 최종 종합점수에서 뒤졌고, 047040은 리스크 점수가 더 높았다.
- fallback trade라면 `상위 후보가 monitor에서 어떤 사유로 막혔고, 차순위가 왜 최종 체결 종목이 됐는지`를 한 줄로 명시한다.

### 진입 상세 근거

진입은 `breakout_above_recent_high_with_vwap_structure_confirmation` 조건으로 실행됐다. 즉 전략가는 눌림목 프레임을 유지했지만, 실제 엔트리는 돌파 확인형에 가까웠다.

- 적용 정책: timeframe 1분, breakout_lookback 4, volume_ratio_min 0.73
- 진입가: 1,160,000원
- 해석: 종목 선택 논리와 진입 방식이 완전히 충돌하는 것은 아니지만, 눌림목 관점 대비 다소 늦은 확인 진입으로 읽힌다.
- 진단 포인트: 이 거래의 핵심 리스크는 종목 선정 실패보다 entry timing 품질 저하 가능성이다.

### 보유 경과

보유 시간은 1분 3초로 매우 짧았다. 모니터는 총 6회 실행됐고, 핵심 감시 축은 `peak_drawdown`이었다. 이 섹션은 progression만 설명하고 truth 값은 다시 반복하지 않는다.

- hold duration: 1분 3초
- peak price: 1,162,000원
- current/exit price: 1,162,000원
- peak_drawdown: -1.16%
- 해석: 진입 직후 기대한 방향 지속성이 약했고, 수익 구간을 충분히 만들기 전에 흔들림 관리 국면으로 넘어갔다.
- 진단: 보유 단계 실패라기보다, entry 직후 포지션이 안정화될 시간을 확보하지 못한 거래에 가깝다.

### 청산 판단 근거

청산은 `peak_drawdown` 트리거로 발생했다. 중요한 점은 이번 청산이 `고정 손절 3.00% 도달`이 아니라, 장중 고점 대비 되밀림 감시 축에서 먼저 나왔다는 점이다. 모니터 관측값은 이 섹션에서 보조 근거로만 설명하고, 실현손익은 Truth Surface를 우선한다고 분리해서 쓴다.

- canonical exit reason: peak_drawdown
- 유효 손절 기준: 3.00%
- 목표 수익 기준: 3.42%
- 해석: 절대 손절선이 깨져서 나간 거래가 아니라, 짧은 반등 후 탄력이 이어지지 못해 관리형 청산이 실행된 거래다.
- 진단: exit bug로 보기보다, entry 이후 follow-through가 약했던 케이스로 읽는 편이 맞다.

### 결과 평가

이 거래는 `시장 해석 실패`보다 `진입 품질 문제 가능성`이 더 크다. 시장, 전략가, 스캐너 레이어는 비교적 일관됐지만, 실제 진입 후 1분 내 `peak_drawdown` 청산이 발생했다는 점에서 타이밍 리스크가 더 크게 드러났다. 당일 reporter 집계는 이 평가를 보조하는 근거로만 쓴다.

- scanner quality: 양호
- strategist context: 양호
- entry timing: 재점검 필요
- hold evidence: 짧아서 판단 제한적
- exit logic: 규칙상 정상 작동
- day-level reporter feedback이 있다면 `당일 손실 누적`, `cached strategist 재사용 비중`, `guard blocker 집중` 같은 구조적 패턴을 보조 근거로만 붙인다.

### 보완 사안

이 섹션은 trade-specific weakness와 운영 후속 확인 항목을 적는다. 이미 reporter가 연결된 거래라면 `same-day reporter 미연계` 같은 stale 문구는 숨겨야 한다.

- 보유 구간 근거가 얇아 진입과 청산 사이 모니터 문맥을 더 보존해야 한다.
- same-day reporter가 이미 연결된 거래라면 중복 follow-up 문구를 넣지 않는다.
- partial trade artifact나 ghost trade처럼 lifecycle이 불완전한 경우는 `_health.json` 기준으로 명시하고 정상 리포트와 섞지 않는다.

### 최종 운영 판단

이 섹션은 "지금 무엇을 보면 되는가"를 한 문단으로 정리한다. 숫자 truth와 동일한 값을 반복하는 대신, 현재 액션과 다음 체크 포인트를 운영자 문장으로 닫는다.

- 현재 판단은 청산 완료다.
- 이 거래는 종목 선정 실패보다 진입 타이밍 부담이 더 컸다.
- 다음 확인 항목은 이번 청산이 방어적으로 타당했는지, 과도한 노이즈 청산은 아니었는지 복기하는 것이다.
- 재진입은 쿨다운 이후 새 스캐너 확인이 있을 때만 검토한다.

## 이 예시가 의미하는 것

- `Truth Surface`는 브로커 truth와 monitor 관측을 분리해서 보여줘야 한다.
- 메모리 섹션은 `prompt-proven / reconstructed / deterministic applied bias` 세 층으로 나눠야 한다.
- `시장 환경 요약`은 헤드라인 나열이 아니라 시장 판단 축을 정리해야 한다.
- `전략가 요약`은 `입력 -> 해석 -> 스캐너 반영 -> 종목 선택` 구조여야 한다.
- `선택된 종목 상세 분석`과 `스캐너 후보 비교`는 중복 없이 역할을 나눠야 한다.
- `결과 평가`는 당일 집계 dump가 아니라 이번 거래의 책임 축을 먼저 설명해야 한다.
- `local_debug` 재생성은 live 생성본을 덮어쓰지 않고 별도 산출물로 남아야 한다.
