# M10: Live Pipeline (stateful, end-to-end)

M10은 **실행 파이프라인을 “고정 배선(wiring)”** 해서, `state.json`(persisted state) + (시장/포트폴리오) snapshot + decision packet을 한 번에 처리합니다.

## 파이프라인 순서

`graphs/pipelines/m10_live_pipeline.py`

1. **load_state**
   - `STATE_STORE_PATH`(기본: `./data/state.json`)에서 persisted state 로드
   - 결과: `state["persisted_state"]`

2. **build_snapshots**
   - 시장/포트폴리오 스냅샷 생성
   - 기본 reader:
     - `KiwoomPriceReader.from_env()` (현재가)
     - `KiwoomPortfolioReader.from_env()` (현금/보유종목)
   - 테스트/로컬에서는 `state["price_reader"]`, `state["portfolio_reader"]` 주입 가능
   - 결과: `state["market_snapshot"]`, `state["portfolio_snapshot"]`, `state["snapshots"]`

3. **build_risk_context**
   - snapshot + persisted state로 risk context 산출
   - 결과: `state["risk_context"]`
   - 주요 필드: `open_positions`, `daily_pnl_ratio`, `last_order_epoch`, `now_epoch`

4. **execute_from_packet**
   - `state["decision_packet"]`을 실행 가능한 요청으로 변환/검증 후 executor로 실행
   - **Supervisor(감독관)** 이 allow/block 결정 (human 승인 없음)
   - executor 주입 가능: `state["executor"]` (테스트용)
   - 결과: `state["execution"]`
     - 최소 규약: `allowed: bool`, `payload: dict`

5. **update_state_after_execution**
   - 실행 결과를 기반으로 persisted state 업데이트
   - 예: `last_order_epoch`, 포지션/쿨다운 관련 값 갱신
   - 결과: `state["persisted_state"]` 갱신

6. **save_state**
   - persisted state를 `STATE_STORE_PATH`에 저장

## 입력/출력 계약

### 입력 (최소)
- `state["symbol"]`
- `state["decision_packet"]`  
  (M11에서 생성하거나, 테스트처럼 외부에서 주입)

### 출력 (핵심)
- `state["snapshots"]`
- `state["risk_context"]`
- `state["execution"]`
- `state["persisted_state"]`

## 테스트
- `tests/test_m10_live_pipeline.py`가 end-to-end 구조(주입 reader/executor 포함)를 검증합니다.
