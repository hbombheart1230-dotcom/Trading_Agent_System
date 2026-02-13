# Project Tree – Trading_Agent_System (Repo 기준 전체판)

> 기준: GitHub repo 구조(현 시점 zip 기준)  
> 목적: 프로젝트의 **전체 폴더/파일 구성**과 **역할**, 그리고 **확장 포인트(M17 Graph Spine)**를 한 곳에서 확인

---

## 1) 전체 트리 (depth<=4)

```text
Trading_Agent_System - 복사본/
├─ config/
│  ├─ skills/
│  │  ├─ account.orders.yaml
│  │  ├─ market.quote.yaml
│  │  ├─ order.place.yaml
│  │  └─ order.status.yaml
│  └─ .env.example
├─ data/
│  ├─ logs/
│  │  ├─ events.jsonl
│  │  └─ intents.jsonl
│  ├─ originals/
│  │  ├─ - 복사본.env
│  │  └─ 키움 REST API 문서.xlsx
│  ├─ specs/
│  │  ├─ api_catalog.jsonl
│  │  ├─ default_rules.json
│  │  ├─ kiwoom_api_list_tagged.jsonl
│  │  └─ kiwoom_apis.jsonl
│  ├─ m15_demo_events.jsonl
│  ├─ m15_demo_intents.jsonl
│  └─ token_cache.json
├─ docs/
│  ├─ en/
│  │  ├─ 00_index.md
│  │  ├─ 01_overview.md
│  │  ├─ 02_principles.md
│  │  ├─ 03_context_and_scope.md
│  │  ├─ 04_logical_architecture.md
│  │  ├─ 05_runtime_flow.md
│  │  ├─ 06_contracts.md
│  │  ├─ 07_execution_and_guards.md
│  │  ├─ 08_observability.md
│  │  ├─ 09_security_and_compliance.md
│  │  ├─ 10_deployment_and_ops.md
│  │  ├─ 11_testing_and_quality.md
│  │  ├─ 12_roadmap.md
│  │  └─ 99_glossary.md
│  └─ ko/
│     ├─ 00_index.md
│     ├─ 01_overview.md
│     ├─ 02_principles.md
│     ├─ 03_context_and_scope.md
│     ├─ 04_logical_architecture.md
│     ├─ 05_runtime_flow.md
│     ├─ 06_contracts.md
│     ├─ 07_execution_and_guards.md
│     ├─ 08_observability.md
│     ├─ 09_security_and_compliance.md
│     ├─ 10_deployment_and_ops.md
│     ├─ 11_testing_and_quality.md
│     ├─ 12_roadmap.md
│     └─ 99_glossary.md
├─ graphs/
│  ├─ nodes/
│  │  ├─ assemble_decision_packet.py
│  │  ├─ build_market_snapshot.py
│  │  ├─ build_portfolio_snapshot.py
│  │  ├─ build_risk_context.py
│  │  ├─ build_snapshots.py
│  │  ├─ decide_trade.py
│  │  ├─ ensure_token.py
│  │  ├─ execute_from_packet.py
│  │  ├─ execute_order.py
│  │  ├─ load_state.py
│  │  ├─ log_decision_trace.py
│  │  ├─ plan_api.py
│  │  ├─ prepare_api_call.py
│  │  ├─ prepare_order_dry_run.py
│  │  ├─ read_account_balance.py
│  │  ├─ save_state.py
│  │  ├─ scan_candidates.py
│  │  ├─ select_candidate.py
│  │  └─ update_state_after_execution.py
│  └─ pipelines/
│     ├─ m10_live_pipeline.py
│     ├─ m11_2_live_pipeline.py
│     ├─ m11_live_pipeline.py
│     ├─ m13_eod_report.py
│     ├─ m13_live_loop.py
│     └─ m13_tick.py
├─ libs/
│  ├─ agent/
│  │  ├─ executor/
│  │  │  ├─ __init__.py
│  │  │  ├─ agent_executor.py
│  │  │  └─ executor_agent.py
│  │  ├─ __init__.py
│  │  ├─ commander.py
│  │  ├─ executor.py
│  │  ├─ intent_parser.py
│  │  ├─ monitor.py
│  │  ├─ reporter.py
│  │  ├─ router.py
│  │  ├─ scanner.py
│  │  └─ strategist.py
│  ├─ ai/
│  │  ├─ providers/
│  │  │  ├─ __init__.py
│  │  │  └─ openai_provider.py
│  │  ├─ intent_schema.py
│  │  ├─ strategist.py
│  │  └─ strategist_factory.py
│  ├─ catalog/
│  │  ├─ __init__.py
│  │  ├─ api_catalog.py
│  │  ├─ api_discovery.py
│  │  ├─ api_planner.py
│  │  └─ api_request_builder.py
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ api_response.py
│  │  ├─ event_logger.py
│  │  ├─ event_logger_compat.py
│  │  ├─ http_client.py
│  │  └─ settings.py
│  ├─ execution/
│  │  ├─ executors/
│  │  │  ├─ __init__.py
│  │  │  ├─ base.py
│  │  │  ├─ factory.py
│  │  │  ├─ mock_executor.py
│  │  │  └─ real_executor.py
│  │  ├─ __init__.py
│  │  └─ order_client.py
│  ├─ kiwoom/
│  │  ├─ __init__.py
│  │  ├─ kiwoom_account_client.py
│  │  ├─ kiwoom_token_client.py
│  │  └─ token_cache.py
│  ├─ read/
│  │  ├─ __init__.py
│  │  ├─ kiwoom_portfolio_reader.py
│  │  ├─ kiwoom_price_reader.py
│  │  ├─ portfolio_reader.py
│  │  ├─ price_reader.py
│  │  └─ snapshot_models.py
│  ├─ reporting/
│  │  ├─ __init__.py
│  │  └─ daily_report.py
│  ├─ risk/
│  │  ├─ __init__.py
│  │  ├─ intent.py
│  │  └─ supervisor.py
│  ├─ runtime/
│  │  ├─ __init__.py
│  │  ├─ dates.py
│  │  └─ market_hours.py
│  ├─ skills/
│  │  ├─ __init__.py
│  │  ├─ dto.py
│  │  ├─ dto_extractors.py
│  │  ├─ registry.py
│  │  ├─ rules.py
│  │  └─ runner.py
│  ├─ storage/
│  │  ├─ __init__.py
│  │  ├─ proposal_store.py
│  │  └─ state_store.py
│  ├─ supervisor/
│  │  ├─ __init__.py
│  │  ├─ intent_store.py
│  │  └─ two_phase.py
│  ├─ tools/
│  │  ├─ __init__.py
│  │  ├─ tool_facade.py
│  │  └─ tool_schema.py
│  └─ __init__.py
├─ scripts/
│  ├─ __init__.py
│  ├─ build_api_catalog.py
│  ├─ build_default_rules.py
│  ├─ demo_m14_mock_order.py
│  ├─ demo_m14_order_status.py
│  ├─ demo_m14_quote_then_order.py
│  ├─ demo_m15_smoke.py
│  ├─ demo_m7_dry_run_pipeline.py
│  ├─ generate_daily_report.py
│  ├─ run_m13_live_loop.py
│  └─ run_m15_matrix.py
├─ tests/
│  ├─ test_account_client.py
│  ├─ test_api_catalog.py
│  ├─ test_api_discovery.py
│  ├─ test_api_planner.py
│  ├─ test_api_request_builder.py
│  ├─ test_api_response.py
│  ├─ test_build_api_catalog.py
│  ├─ test_build_risk_context.py
│  ├─ test_daily_report.py
│  ├─ test_event_logger.py
│  ├─ test_execute_from_packet.py
│  ├─ test_http_client.py
│  ├─ test_intent_packet.py
│  ├─ test_kiwoom_token_client.py
│  ├─ test_load_save_state_nodes.py
│  ├─ test_m10_live_pipeline.py
│  ├─ test_m11_2_scanner.py
│  ├─ test_m11_live_pipeline.py
│  ├─ test_m12_1_provider_routing.py
│  ├─ test_m12_2_openai_http_provider.py
│  ├─ test_m12_3_intent_normalization.py
│  ├─ test_m12_strategist_hook.py
│  ├─ test_m13_e2e_once.py
│  ├─ test_m13_eod_report.py
│  ├─ test_m13_live_loop.py
│  ├─ test_m13_tick.py
│  ├─ test_m15_smoke.py
│  ├─ test_m7_demo_catalog.py
│  ├─ test_m9_build_snapshots.py
│  ├─ test_m9_real_portfolio_reader.py
│  ├─ test_m9_real_price_reader.py
│  ├─ test_m9_snapshots.py
│  ├─ test_mock_executor.py
│  ├─ test_order_client.py
│  ├─ test_real_executor_disabled.py
│  ├─ test_real_executor_mock_mode_allowed.py
│  ├─ test_settings.py
│  ├─ test_state_store.py
│  ├─ test_supervisor.py
│  ├─ test_symbol_allowlist_guard.py
│  ├─ test_token_cache.py
│  └─ test_update_state_after_execution.py
├─ .gitignore
├─ auto_push.bat
├─ conftest.py
├─ README.md
└─ requirements.txt
```

> 참고: `.git`, `__pycache__`, `venv/.venv` 등은 가독성을 위해 제외

---

## 2) 핵심 디렉토리 설명

### config/
- `.env.example`: 실행 환경 템플릿
- `skills/*.yaml`: Skill 스펙(요청/응답/엔드포인트/가드 등) 정의

### data/
- `originals/`: 원본 자료(런타임 미사용, 재가공용)
- `specs/`: 정규화된 API 스펙(카탈로그, 룰 등)
- `logs/`: 실행/의사결정 로그(JSONL), intent journal

### libs/
- 핵심 런타임/도메인 로직
- settings / guards / supervisor / execution / skills / event logger 등

### graphs/
- **파이프라인/노드 계층**
- `nodes/`: 단일 단계 노드(스냅샷, 토큰, 결정, 실행 등)
- `pipelines/`: 노드 조합으로 만든 실행 파이프라인 (m10~m13 등)

### scripts/
- 데모/운영 스크립트

### tests/
- pytest 테스트 모음 (M1~M16 포함)

---

## 3) M17 (B안) 확장 포인트: Graph Spine

M17의 목적은 “그래프를 시스템 Spine(척추)로 승격”하는 것.

- `graphs/trading_graph.py` (신규): **단일 진입점** + **조건 분기(approve/reject/noop)**의 기본 트리
- `graphs/nodes/*_node.py` (신규): 기존 agent layer를 **node wrapper**로 연결하는 표준 레이어

### 기본 흐름(B)
```
Strategist -> Scanner -> Monitor -> Decision
  approve -> Executor(stub: execution_pending=True)
  noop/reject -> END
```

> 실행(주문)은 Supervisor/ApprovalService/Execution Layer가 담당하고,  
> Graph는 “흐름 + 상태”만 담당한다.

---

## 4) 운영 원칙(요약)
- **가드가 최상위 우선순위**: EXECUTION_ENABLED=false면 어떤 경로로도 주문 불가
- **approve != execute**: 승인과 실행을 분리해서 안전성/재현성 확보
