# Read-only UI, Docker, Kubernetes 검토 및 구현 계획

> 운영·포트폴리오 제품 범위, Q9-Q18 데이터 활용 방식, 현재 연구 연결,
> 화면 구성과 구현 마일스톤의 최신 권위는
> `docs/web_observability/combined_milestone_plan_2026-08-14.md`이다.
> 구현 격리와 모듈화의 최우선 하드 계약은
> `docs/web_observability/isolation_and_modularity_contract.md`이다.
>
> 이 문서의 기존 `Validation / Runs / Events / System` 중심 화면 제안은
> 개발자 관측 도구 성격이 강하므로 제품 UI 권위에서 제외한다. Q9~Q18과
> 현재 연구는 `Performance / Trades / Opportunities / Strategies / Market /
> Data Quality`를 구성하는 내부 데이터 근거로 사용하며, 평가 진행 과정
> 자체는 MVP 주 메뉴에 노출하지 않는다.

## 1. 검토 결론

판정: **조건부 진행 권장**

첨부안의 핵심 방향은 타당하다.

- Trading Core와 평가 로직은 그대로 둔다.
- 기존 산출물만 읽는 별도 관측 계층을 만든다.
- API와 UI에는 주문, 승인, 설정 변경 기능을 두지 않는다.
- Docker와 Kubernetes에는 Trading Core를 넣지 않는다.

다만 첨부안을 그대로 신규 구현하면 현재 저장소와 중복되거나 운영상 문제가 생긴다. 다음 보정이 필요하다.

1. 기존 `apps/operator_ui`는 새 API의 기반으로 재사용하지 않는다.
2. Q13/Q14의 공식 Validation 결과와 최신 일별 Q13/Q14 결과를 구분한다.
3. 0.8GB~9.5GB JSONL을 요청마다 전체 검색하지 않는다.
4. Windows 호스트 데이터를 Kubernetes에 연결하는 방식은 local overlay에서만 정의한다.
5. UI에 표시하는 Trading Runtime 상태와 Web 자체의 read-only 상태를 분리한다.
6. API image에는 `libs/agent`, `libs/execution`, `graphs`를 포함하지 않는다.

이 문서는 설계 검토 결과다. 현재 단계에서는 코드, 런타임, 매매 동작을 변경하지 않는다.

## 2. 현재 저장소 확인 결과

| 항목 | 확인 결과 | 판단 |
| --- | --- | --- |
| Repository root | `C:/Trading_Agent_System` | 확정 |
| Python | 3.14.2 | 로컬 환경 기준. Container는 3.12 계열 권장 |
| Python dependencies | 루트 `requirements.txt`에 FastAPI, Jinja2, Uvicorn, HTTPX 존재 | 새 API는 별도 최소 requirements 사용 |
| 기존 Web | `apps/operator_ui`의 FastAPI + Jinja UI 존재 | 신규 read-only 관측면과 분리 |
| React/Vite | `package.json`, Node 프로젝트 없음 | `apps/web`에 신규 구성 필요 |
| Docker | Dockerfile, Compose 파일 없음 | 신규 구성 필요 |
| Kubernetes | Kustomize/Kubernetes manifest 없음 | 신규 구성 필요 |
| Docker CLI | 현재 호스트에서 확인되지 않음 | 구현 후 smoke test 전 설치 필요 |
| kubectl | 현재 호스트에서 확인되지 않음 | Kubernetes 검증 전 설치 필요 |
| Node/npm | 현재 호스트에서 확인되지 않음 | UI build 전 설치 또는 Docker build 사용 |
| `.env` | 존재하지만 Git에서 ignore되고 추적되지 않음 | 유지. Container에 mount 금지 |
| `reports/` | Git ignore, 런타임 산출물로 존재 | read-only mount 대상 |
| `data/logs/` | Git ignore, 런타임 로그 존재 | read-only mount 대상 |
| `data/evidence_ledger/` | Git ignore, 별도 evidence JSONL 존재 | 필요 시 별도 read-only mount |

### 2.1 현재 데이터 크기

2026-08-14 확인 기준:

| 파일 | 크기 | 영향 |
| --- | ---: | --- |
| `data/logs/events.jsonl` | 약 0.8GB | 매 요청 전체 검색 금지 |
| `data/evidence_ledger/events.jsonl` | 약 5.9GB | 기본 API 조회 대상에서 제외 |
| `data/logs/archive/events_20260626_...jsonl` | 약 9.5GB | Web API에서 직접 검색 금지 |
| `reports/operator_summary/daily/2026-08-13/q9_decision_windows.json` | 약 82MB | 일반 report detail 크기 제한 필요 |

대용량 파일을 동기식으로 전체 파싱하면 API 응답 지연, 메모리 급증, Trading Runtime 디스크 I/O 간섭이 발생할 수 있다.

## 3. 기존 Operator UI 재사용 판단

`apps/operator_ui`는 화면 디자인 참고 대상으로는 사용할 수 있지만, 신규 read-only API의 코드 기반으로 사용하지 않는다.

근거:

- `libs.reporting`을 import한다.
- `libs.llm`과 `LLMRouter`를 import한다.
- GET 상세 조회 과정에서 Operator Brief를 생성할 수 있다.
- 캐시와 리포트 JSON/Markdown을 기록하는 코드가 있다.
- lifecycle bundle을 수정하는 호환성 코드가 있다.
- `run_id` 조회 시 대형 JSONL을 전체 순회한다.

즉 HTTP method가 GET이어도 filesystem 및 LLM side effect가 발생할 수 있다. 첨부안의 엄격한 read-only 정의와 맞지 않는다.

결정:

- 기존 `apps/operator_ui/**`는 수정하지 않는다.
- 신규 `apps/api/**`는 `apps/operator_ui`를 import하지 않는다.
- 신규 `apps/api/**`는 `libs/**`, `graphs/**`, `scripts/**`를 import하지 않는다.
- 필요한 파일 해석은 신규 reader에서 독립적으로 수행한다.
- 기존 UI와 신규 UI는 전환이 완료될 때까지 병존할 수 있다.

## 4. 목표 아키텍처

```text
Existing Trading Agent System (Windows host)
  -> reports/
  -> data/logs/
  -> data/evidence_ledger/ (optional)

Read-only bind mounts
  -> FastAPI display adapter
  -> React/Vite static Web
  -> Browser
```

금지되는 역방향 경로:

```text
Web/API -X-> Commander
Web/API -X-> Strategist/Scanner/Monitor
Web/API -X-> Executor/Kiwoom
Web/API -X-> Q13/Q14 generator
Web/API -X-> reports/logs mutation
```

## 5. 데이터 권위 매핑

API는 새 계산을 하지 않고 다음 기존 파일을 표시용으로 정규화한다.

### 5.1 Q13 일별 권위

```text
reports/evaluation/daily/<day>/attribution_score_v0.json
```

확인된 schema:

```text
attribution_score_v0.v1
```

주요 축:

- `selection_integrity_score`
- `scanner_alignment_score`
- `entry_timing_score`
- `exit_horizon_score`
- `evidence_quality_score`

### 5.2 Q14 일별 권위

```text
reports/evaluation/daily/<day>/scanner_alignment_root_cause_report.json
```

확인된 schema:

```text
scanner_alignment_root_cause.v1
```

주요 필드:

- `trade_count`
- `cause_summary`
- `largest_observed_root_cause`
- `largest_behavior_root_cause`
- `largest_structural_root_cause`
- `q15_behavior_patch_candidate`

### 5.3 Q13/Q14 공식 Validation 권위

```text
reports/evaluation/validation/<validation_id>/q13_q14_validation_report.json
reports/evaluation/validation/<validation_id>/q13_q14_validation_report.md
```

확인된 schema:

```text
q13_q14_validation.v1
```

주요 필드:

- `days`
- `required_validation_days`
- `day_count`
- `completed_report_day_count`
- `total_trade_count`
- `root_cause_totals`
- `missing_evidence_ratio`
- `decision`
- `decision_reasons`
- `daily_rows`

### 5.4 보조 일별 권위

```text
reports/evaluation/daily/<day>/q9_day_validity.json
reports/evaluation/daily/<day>/daily_scorecard.json
reports/evaluation/daily/<day>/horizon_compliance_report.json
reports/evaluation/daily/<day>/entry_timing_attribution_report.json
reports/evaluation/daily/<day>/selection_authority_audit.json
reports/operator_summary/daily/<day>/operator_summary.json
reports/operator_summary/daily/<day>/q9_decision_windows.json
```

### 5.5 중요한 상태 구분

`latest formal validation`과 `latest daily observation`은 같은 개념이 아니다.

- Formal validation: 마지막으로 명시적으로 생성한 다일 Validation 결과
- Daily observation: 가장 최근 거래일의 Q13/Q14 산출물

UI가 오래된 formal validation을 현재 진행 상태로 오인하면 안 된다. 두 시각과 대상 기간을 모두 표시한다.

## 6. API 설계 원칙

### 6.1 공통 응답 계약

모든 조회 응답은 가능한 범위에서 다음 envelope를 사용한다.

```json
{
  "status": "AVAILABLE",
  "source": {
    "artifact_type": "q13_daily",
    "schema_version": "attribution_score_v0.v1",
    "observed_at": "2026-08-13"
  },
  "data": {},
  "warnings": []
}
```

상태 값:

- `AVAILABLE`
- `PARTIAL`
- `UNAVAILABLE`
- `MALFORMED`
- `TOO_LARGE`

없는 값을 추정하지 않는다. 근거가 없으면 `null`과 명시적 reason을 반환한다.

### 6.2 Health

```text
GET /health/live
GET /health/ready
```

- `live`: API process가 응답 가능한지만 확인한다.
- `ready`: 설정된 reports/log roots가 존재하고 읽을 수 있는지 확인한다.
- Kiwoom, Trading Runtime, 최신 Validation 존재 여부는 liveness 조건이 아니다.
- 데이터가 아직 없더라도 mount가 정상이라면 ready일 수 있다.

### 6.3 System Status

```text
GET /api/v1/system/status
```

표시 개념을 분리한다.

```json
{
  "web": {
    "read_only": true,
    "execution_callable": false
  },
  "trading_runtime": {
    "mode": "mock",
    "execution_enabled": null,
    "approval_mode": null,
    "source": "configured_display_metadata"
  },
  "validation": {
    "formal_decision": "RETAIN",
    "latest_daily_status": "AVAILABLE"
  }
}
```

주의:

- Web의 `execution_callable=false`와 Trading Runtime의 `execution_enabled`는 다르다.
- `.env`를 API Pod에 mount해서 값을 읽지 않는다.
- ConfigMap으로 전달한 표시용 값은 `configured_display_metadata`로 출처를 표시한다.
- 기존 artifact에서 확정할 수 없는 값은 `null`로 둔다.

### 6.4 Validation

```text
GET /api/v1/validation/q13-q14/latest
GET /api/v1/validation/q13-q14/history
```

`latest` 응답에는 다음을 분리한다.

- latest formal validation
- latest daily Q13
- latest daily Q14
- daily validity
- source dates
- stale 여부

`history`는 formal validation 목록을 최신 순으로 반환하고 pagination을 사용한다. 일별 관측 이력은 query parameter 또는 별도 section으로 구분한다.

API는 Q13/Q14 계산 함수나 report generator를 실행하지 않는다.

### 6.5 Reports

```text
GET /api/v1/reports
GET /api/v1/reports/{report_id}
```

보안 및 성능 계약:

- 허용 root와 확장자를 명시적으로 제한한다.
- 실제 상대 경로를 직접 API id로 사용하지 않는다.
- 시작 시 또는 TTL refresh 시 만든 in-memory `report_id -> resolved path` mapping을 사용한다.
- resolved path가 허용 root 내부인지 매 조회마다 재검증한다.
- symlink escape를 거부한다.
- 기본 허용 확장자는 `.json`, `.md`다.
- response에 host 절대 경로를 노출하지 않는다.
- 기본 detail 크기 제한은 5MB로 둔다.
- 큰 파일은 metadata와 `TOO_LARGE` 상태만 반환한다.
- Markdown은 raw HTML로 실행하지 않는다. 초기 UI에서는 text/preformatted 표시를 우선한다.

권장 report roots:

```text
reports/evaluation
reports/operator_summary
reports/trades
reports/canonical
```

82MB Q9 decision file은 일반 report detail로 전송하지 않는다. 필요한 요약은 더 작은 기존 summary artifact에서 읽는다.

### 6.6 Runs

```text
GET /api/v1/runs
GET /api/v1/runs/{run_id}
```

우선 source:

```text
reports/canonical/<day>/<run_id>/
reports/operator_summary/daily/<day>/q9_decision_windows.json
reports/trades/<day>/...
```

원칙:

- canonical directory를 기반으로 in-memory run index를 만든다.
- index는 API memory에만 존재하며 파일로 기록하지 않는다.
- `run_id`는 허용 문자와 최대 길이를 검증한다.
- run detail은 canonical artifact와 연결된 report metadata만 반환한다.
- 82MB Q9 파일을 모든 detail 요청에서 반복 파싱하지 않는다.
- 필요한 경우 최근 일자만 TTL cache하고 cache는 memory-only로 유지한다.

### 6.7 Events

```text
GET /api/v1/events?run_id=<run_id>
```

현재 로그 크기 때문에 다음 제한이 필수다.

- 기본 source는 `data/logs/events.jsonl` 하나다.
- 기본 검색 범위는 파일 tail 32MB, 최대 64MB다.
- 최대 반환 row는 500개다.
- 최대 line 크기와 최대 JSON depth를 둔다.
- malformed row는 건너뛰고 `malformed_count`를 반환한다.
- 오래된 run이 검색 범위 밖이면 전체 로그를 검색하지 않고 `UNAVAILABLE`을 반환한다.
- 응답에 `coverage=RECENT_TAIL_ONLY`와 scanned bytes를 표시한다.
- 5.9GB evidence ledger와 9.5GB archive는 기본 요청에서 검색하지 않는다.
- payload는 크기 제한과 민감 키 redaction을 거친다.

과거 전체 events 검색이 반드시 필요해질 경우 별도 read-only index 생성 작업으로 분리한다. 이번 범위에서는 state store나 index DB를 만들지 않는다.

## 7. API 보안 경계

필수 통제:

1. API route는 GET만 정의한다.
2. middleware에서 GET/HEAD/OPTIONS 외 method를 405로 거부한다.
3. OpenAPI에도 mutation endpoint가 없어야 한다.
4. API process filesystem은 read-only로 실행한다.
5. reports/log mounts는 모두 `:ro` 또는 `readOnly: true`다.
6. `.env`, Kiwoom key, OpenRouter key를 mount하지 않는다.
7. response에서 token, secret, authorization, app key 계열 필드를 제거한다.
8. host 절대 경로와 stack trace를 response에 포함하지 않는다.
9. 인터넷 및 Kiwoom 호출을 위한 dependency를 API image에 포함하지 않는다.
10. API는 localhost bind 또는 Kubernetes port-forward로만 노출한다.

추가 권장:

- `X-Content-Type-Options: nosniff`
- 제한적인 Content Security Policy
- 같은 origin reverse proxy를 사용해 불필요한 CORS 제거
- query 길이, page size, response size 제한

## 8. 신규 파일 구조 제안

기존 파일 수정 없이 다음 경로에만 추가한다.

```text
apps/
  api/
    __init__.py
    main.py
    config.py
    requirements.txt
    routers/
      health.py
      validation.py
      reports.py
      runs.py
      events.py
      system.py
    services/
      filesystem.py
      validation_reader.py
      report_reader.py
      run_reader.py
      event_reader.py
      system_reader.py
    models/
      common.py
      validation.py
      reports.py
      runs.py
      events.py
      system.py

  web/
    package.json
    tsconfig.json
    vite.config.ts
    index.html
    src/
      app/
      api/
      components/
      pages/
      styles/

deploy/
  docker/
    Dockerfile.api
    Dockerfile.api.dockerignore
    Dockerfile.web
    Dockerfile.web.dockerignore
    nginx.conf
  compose/
    compose.yaml
    .env.example
  k8s/
    base/
    overlays/local/

tests/apps/api/
docs/web_observability/
```

`apps/api/requirements.txt`를 별도로 두어 root `requirements.txt`를 수정하지 않는다.

## 9. Web UI 계획

기술:

- React
- TypeScript
- Vite
- 최소 dependency
- 정적 build + Nginx

화면:

1. Overview
2. Performance
3. Trades
4. Opportunities
5. Strategies
6. Market
7. Reports
8. Data Quality

`Runs`, `Events`, `System` 원문 상세는 Data Quality의 고급 진단으로
내린다. `Validation`은 독립 제품 화면으로 만들지 않는다. Q9~Q18과 현재
shadow 연구는 위 화면을 구성하는 데이터 출처이며, 사용자는 Q 번호가
아니라 수익·거래·기회·전략·시장·이상 징후를 기준으로 탐색한다.

상단 고정 상태:

- `READ ONLY`
- Trading mode와 근거 source
- Web execution callable: `NO`
- 장 상태와 Trading Runtime 상태
- 마지막 정상 데이터 갱신 시각
- broker/report/evaluation 데이터 신뢰 상태

각 panel은 다음 상태를 독립 처리한다.

- Loading
- Available
- Partial
- Unavailable
- No Data
- Error

금지:

- 주문/취소 버튼
- 승인/거절 버튼
- Commander 실행 버튼
- 환경설정 변경 UI
- API key 입력
- execution toggle
- raw Markdown HTML 실행

## 10. Docker 계획

### 10.1 API image

- Python 3.12 slim 권장
- `apps/api/**`와 최소 dependency만 포함
- `libs/**`, `graphs/**`, `scripts/**`, `.env` 미포함
- non-root user
- read-only root filesystem
- `/tmp`만 tmpfs 허용
- Uvicorn single worker로 시작

### 10.2 Web image

- Node build stage
- Nginx runtime stage
- `/api`를 API service로 reverse proxy
- static root read-only
- non-root Nginx image 또는 동등한 보안 설정

### 10.3 Compose mount

Windows 절대 경로를 YAML에 직접 고정하지 않는다.

```yaml
volumes:
  - ${TRADING_REPO_ROOT}/reports:/data/reports:ro
  - ${TRADING_REPO_ROOT}/data/logs:/data/runtime-logs:ro
  - ${TRADING_REPO_ROOT}/data/evidence_ledger:/data/evidence:ro
```

`.env.example`에는 secret 없이 다음 예시만 둔다.

```text
TRADING_REPO_ROOT=C:/Trading_Agent_System
DISPLAY_TRADING_MODE=mock
```

포트:

```text
127.0.0.1:3000 -> web
127.0.0.1:8000 -> api
```

Compose 검증 순서:

```text
docker compose config
docker compose build
docker compose up -d
health/live
health/ready
UI smoke
filesystem write denial check
```

## 11. Kubernetes 계획

Base에는 환경 독립적인 객체만 둔다.

- Namespace
- ConfigMap
- API Deployment, replicas 1
- API ClusterIP Service
- Web Deployment, replicas 1
- Web ClusterIP Service
- Kustomization

Local overlay에만 Docker Desktop hostPath/PV/PVC 연결을 둔다.

이유:

- Windows 경로와 Docker Desktop VM 경로는 환경별로 다르다.
- base에 `C:/Trading_Agent_System`을 하드코딩하면 이식성이 없다.
- 실제 Docker Desktop hostPath 표현은 설치 후 검증해야 한다.

필수 Pod 보안:

- `runAsNonRoot: true`
- `allowPrivilegeEscalation: false`
- `readOnlyRootFilesystem: true`
- capabilities drop ALL
- reports/log volumes `readOnly: true`
- API replicas 1

Probe:

```text
liveness  -> /health/live
readiness -> /health/ready
```

Kiwoom 또는 Trading Runtime 장애를 liveness 실패로 연결하지 않는다.

초기 접근:

```text
kubectl port-forward service/web 3000:80 -n trading-observability
kubectl port-forward service/api 8000:8000 -n trading-observability
```

이번 단계에서는 Ingress, Helm, real overlay, Secret을 만들지 않는다.

## 12. 테스트 계획

### 12.1 API 단위/통합 테스트

모든 테스트는 `tmp_path` fixture만 사용한다.

- health live/ready
- mount 없음/권한 없음
- 정상 Q13/Q14 JSON
- formal validation 없음
- malformed JSON
- unknown schema additive field 보존
- history ordering
- report list/detail
- invalid report id
- traversal 및 symlink escape
- oversized report
- malformed JSONL
- bounded tail coverage
- unknown run id
- secret redaction
- mutation method 405
- no filesystem writes

### 12.2 Import isolation 테스트

신규 API process에서 다음 import가 없어야 한다.

```text
libs.agent
libs.execution
graphs
apps.operator_ui
```

정적 AST/import 검사와 container file inventory 검사를 함께 사용한다.

### 12.3 UI 테스트

- TypeScript typecheck
- production build
- 각 page loading/unavailable/error 상태
- 긴 run id 및 긴 root-cause 문자열 overflow
- raw report HTML 미실행
- mutation control 부재

### 12.4 Container/Kubernetes 테스트

- image 내 금지 경로 부재
- container에서 reports/logs 쓰기 실패
- `.env`와 credential 파일 부재
- healthcheck 통과
- Compose smoke
- `kubectl kustomize` 또는 server-side dry-run
- liveness/readiness 통과
- replicas 1
- volume readOnly 확인

### 12.5 기존 회귀 테스트

신규 테스트 통과 후 기존 전체 suite를 실행한다. 실패 시 Trading Core를 수정하지 않고 신규 adapter/test 문제로 분리한다.

## 13. 단계별 실행 계획

| Phase | 작업 | 완료 gate | Core 변경 |
| --- | --- | --- | --- |
| 0 | 제품 KPI, 권위 경로, 비용 산식, 금지 import manifest 고정 | fixture와 source map 확정 | 없음 |
| 1 | FastAPI skeleton, config, health, 공통 response | health와 isolation tests 통과 | 없음 |
| 2 | Overview/Portfolio/Performance readers | 원본 report 및 broker truth와 수치 일치 | 없음 |
| 3 | Trades/Reports readers | 거래 계보 재구성과 안전한 report 조회 | 없음 |
| 4 | Opportunities/Strategies/Market readers | 표본·coverage·비용 기준 보존 | 없음 |
| 5 | Data Quality 및 bounded diagnostics | 대용량 전체 scan 없음 증명 | 없음 |
| 6 | 운영 중심 React/Vite UI | 주요 업무 흐름과 상태 화면 통과 | 없음 |
| 7 | 포트폴리오 공개 모드와 민감정보 제거 | 공개 profile redaction test 통과 | 없음 |
| 8 | Docker images/Compose | localhost smoke 및 ro mount 통과 | 없음 |
| 9 | Kubernetes base/local overlay | kustomize, probe, port-forward 통과 | 없음 |
| 10 | 전체 회귀 및 Git diff audit | 허용 경로 외 변경 0 | 없음 |

한 번에 전체를 구현하지 않는다. 각 Phase gate가 통과해야 다음 단계로 간다.

## 14. 구현 전 고정할 결정

다음 값은 구현 전에 문서 또는 config contract로 확정한다.

1. report detail 최대 크기: 기본 5MB
2. events tail scan: 기본 32MB, 최대 64MB
3. events 최대 반환: 500 rows
4. report/run index TTL: 권장 30초
5. 운영 KPI와 원본 artifact의 stale 표시 기준
6. UI에 표시할 trading mode의 권위 source
7. Docker Desktop local hostPath 실제 표현

이 값은 Trading 전략이나 평가 산식이 아니라 관측 계층 운영 설정이다.

## 15. Git 변경 경계

향후 허용 변경:

```text
apps/api/**
apps/web/**
deploy/docker/**
deploy/compose/**
deploy/k8s/**
tests/apps/api/**
docs/web_observability/**
```

변경 금지:

```text
libs/agent/**
libs/execution/**
graphs/**
기존 scripts/**
기존 Q13/Q14 코드
기존 evaluation 계산 코드
기존 contracts
기존 logs/reports schema
기존 apps/operator_ui/**
```

각 Phase 종료 시 다음을 확인한다.

```text
git status --short
git diff --name-only
git diff --stat
```

## 16. Blocked / Proposed Changes

### 현재 Blocked

- Docker CLI가 현재 환경에서 확인되지 않았다.
- kubectl이 현재 환경에서 확인되지 않았다.
- Node/npm이 현재 환경에서 확인되지 않았다.
- Docker Desktop Kubernetes의 Windows hostPath 표현을 아직 검증할 수 없다.

이 항목들은 설계와 API Python 테스트를 막지는 않지만 Docker/UI/Kubernetes 실증을 막는다.

### Proposed Changes

- 기존 Trading Core 변경: **None**
- 기존 Q13/Q14 변경: **None**
- 기존 `apps/operator_ui` 변경: **None**
- root `requirements.txt` 변경: **None**
- root `.gitignore` 변경: **None**

## 17. 최종 권장 순서

1. 신규 API를 기존 UI와 완전히 분리한다.
2. KPI·비용·broker truth·기간 집계 계약을 먼저 고정한다.
3. Overview/Performance와 거래 상세 read model을 우선 구현한다.
4. Q9~Q18 및 현재 연구는 Opportunities/Strategies/Data Quality용 내부
   adapter로 연결한다.
5. Reports는 opaque id와 크기 제한을 적용한다.
6. Runs/Events는 고급 진단으로 제한하고 recent-tail만 허용한다.
7. API read-only/import isolation 테스트를 먼저 통과시킨다.
8. 그 뒤 운영·포트폴리오 목적의 React UI를 연결한다.
9. 민감정보를 제거한 공개 profile을 검증한다.
10. Docker Compose를 검증한다.
11. 마지막으로 Docker Desktop Kubernetes local overlay를 검증한다.

이 순서라면 Trading Runtime과 Q13/Q14 평가 결과를 건드리지 않으면서도, 향후 Docker/Kubernetes 환경에서 Codex가 API/UI 관측 서비스를 명령줄로 시작·중지·상태 확인할 수 있는 기반을 만들 수 있다.
