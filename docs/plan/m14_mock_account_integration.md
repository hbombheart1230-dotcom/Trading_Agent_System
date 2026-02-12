# M14: 모의계좌(실통신) 실행 설정

목표: 키움 **모의투자 계좌(가상잔고 1억)** 에 **실제 HTTP 요청**을 보내서
- 토큰 발급/캐시
- 가격/잔고 조회
- 주문(실제 모의주문)

까지 “실전과 동일한 흐름”으로 돌린다.

> 여기서 말하는 `mock`는 내부 테스트용 MockExecutor가 아니라, 키움의 **모의투자 서버(mockapi.kiwoom.com)** 를 의미한다.

---

## 1) 조합 규칙

- `EXECUTION_MODE`
  - `mock`: 내부 `MockExecutor` 사용(테스트/오프라인)
  - `real`: 내부 `RealExecutor` 사용(실제 HTTP 통신)

- `KIWOOM_MODE`
  - `mock`: base_url = `https://mockapi.kiwoom.com` (키움 모의투자)
  - `real`: base_url = `https://api.kiwoom.com` (키움 실전)

따라서
- **모의계좌 실통신** = `EXECUTION_MODE=real` + `KIWOOM_MODE=mock`
- **실전 실통신** = `EXECUTION_MODE=real` + `KIWOOM_MODE=real`

---

## 2) env 설정 (중요: 여기부터 맞추면 된다)

`config/.env.example` 를 복사해서 `.env`를 만들고 아래를 채운다.

필수
- `KIWOOM_APP_KEY`, `KIWOOM_APP_SECRET`
- `KIWOOM_ACCOUNT_NO` (모의계좌 번호)
- `KIWOOM_API_CATALOG_PATH` (api_catalog.jsonl 경로)
- `EXECUTION_MODE=real`
- `KIWOOM_MODE=mock`

권장
- `EVENT_LOG_PATH=./data/logs/events.jsonl`
- `STATE_STORE_PATH=./data/state/state.json`

예시

```bash
# 키움
KIWOOM_MODE=mock
KIWOOM_APP_KEY=...
KIWOOM_APP_SECRET=...
KIWOOM_ACCOUNT_NO=8119....

# catalog
KIWOOM_API_CATALOG_PATH=./data/specs/api_catalog.jsonl

# 실행
EXECUTION_MODE=real

# 로그/상태
EVENT_LOG_PATH=./data/logs/events.jsonl
STATE_STORE_PATH=./data/state/state.json
```

---

## 3) 코드에서 실제 통신이 일어나는 지점

- `libs/execution/executors/real_executor.py`
  - `KiwoomTokenClient` 로 토큰 확보
  - `HttpClient` 로 request 전송

- `graphs/nodes/execute_from_packet.py`
  - intent에서 `api_id`를 얻고
  - `ApiCatalog`에서 ApiSpec 로드
  - `ApiRequestBuilder.prepare(spec, ctx)`로 PreparedRequest 생성
  - executor에 전달

---

## 4) 빠른 검증 루틴

1. `pytest -q` 전체 통과(현재 OK)
2. `.env` 세팅 후 실행
3. 실행 후 `data/logs/events.jsonl` 에서
   - execute_from_packet 단계 로그
   - token 발급/요청 결과
   를 확인

---

## 5) 다음 고도화(모의 1~2달 운용)

- 이벤트 로그/리포트 기반으로
  - 리스크 룰 강화 (`libs/risk/*`)
  - 전략(룰 → LLM) 점진적 전환 (`libs/ai/*`)
  - 조건검색 같은 스킬은 “구현만 해두고”, 실전에서 적용 여부 결정
