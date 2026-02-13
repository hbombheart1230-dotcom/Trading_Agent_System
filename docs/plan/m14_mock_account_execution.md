# M14: 모의계좌(키움 MOCK API) 실통신 + 실주문(모의) 연결

## 지금까지 상황
- M13까지: **테스트 기반으로 전체 파이프라인이 연결**되어 있음
  - snapshot 읽기 → decide_trade(전략가) → supervisor → execute_from_packet → state 업데이트 → 보고서
- 다만, 기존 `EXECUTION_MODE=mock` 는 **내부 MockExecutor**(네트워크 없이 가짜 응답)라서
  키움의 **실제 모의투자 REST 서버(`https://mockapi.kiwoom.com`)**와 통신하지 않는다.

## M14 목표
1) **키움 MOCK REST 서버에 진짜로 붙어서**
   - 토큰 발급/갱신
   - 주문 API 호출(모의 주문)
2) 향후 live loop에서 `EXECUTION_MODE=real` 로 바꿔도
   *모의 서버*에 안전하게 주문이 나가도록 준비.

> 중요: `KIWOOM_MODE=mock` 이면 base_url은 mockapi로 고정되며,
> 실제 돈은 나가지 않는다(키움 모의 계좌 기준).

## ENV 권장값
모의계좌로 “진짜 통신/주문”을 하려면 아래처럼 맞춘다.

```env
KIWOOM_MODE=mock
EXECUTION_MODE=real

# 토큰/주문에 필요
KIWOOM_APP_KEY=...
KIWOOM_APP_SECRET=...
KIWOOM_ACCOUNT_NO=...

# 로그/상태
EVENT_LOG_PATH=./data/logs/events.jsonl
STATE_STORE_PATH=./data/state.json
```

### EXECUTION_ENABLED는 왜 있나?
- `EXECUTION_ENABLED=false`이면 **EXECUTION_MODE가 real이어도** 실행이 차단된다.
- "실수 방지용 세이프티 스위치"로 남겨두는 편이 안전하다.
  - 모의에서 실제로 주문 테스트할 때만 `true`
  - 평소엔 `false`로 두고 파이프라인만 돌릴 수도 있음

## 이번에 추가한 실행 확인 스크립트
- `scripts/demo_m14_mock_order.py`

### 1) api_catalog 생성
현재 카탈로그는 `data/specs/kiwoom_apis.jsonl`에서
`scripts/build_api_catalog.py`로 `data/specs/api_catalog.jsonl`를 만든다.

이때 원본 스펙 필드가 `endpoint/http_method` 형태라서,
카탈로그 생성 시 **endpoint→path**, **http_method→method**로 정규화한다.

### 2) 주문 요청
키움 모의 주문은 샘플 스펙에서 다음 api_id를 사용한다.
- 매수: `kt10000` (`POST /api/dostk/ordr`)
- 매도: `kt10001` (`POST /api/dostk/ordr`)

스크립트는 스펙에 들어있는 example payload를 기반으로 최소 필수 body를 만든다.

## 실행 예시

```bash
# 모의 계좌로 삼성전자 1주, 70,000원 지정가 매수
python scripts/demo_m14_mock_order.py --symbol 005930 --qty 1 --price 70000 --side buy

# 매도
python scripts/demo_m14_mock_order.py --symbol 005930 --qty 1 --price 71000 --side sell
```

성공하면 콘솔에 응답 payload 일부가 출력되고,
`EVENT_LOG_PATH` 위치에 이벤트가 누적된다.

## 다음 단계(M14-4/M15 아이디어)
- `build_portfolio_snapshot`가 실계좌/모의계좌에서 읽어오는 값으로
  state의 `risk_context`를 자동 업데이트
- live loop에서:
  - `EXECUTION_ENABLED`를 켠 상태에서만 주문
  - 그 외에는 dry-run + 로그만
- 주문 결과(접수번호, 체결/미체결)를 `state_store`에 반영
