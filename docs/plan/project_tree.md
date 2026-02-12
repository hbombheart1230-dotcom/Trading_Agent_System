# Project Tree – Trading_Agent_System
*(M15 구조 반영)*

이 문서는 Trading_Agent_System 프로젝트의 **폴더 구조와 각 파일의 역할**을 한눈에 이해하기 위한 가이드이다.  
본 프로젝트는 **Agentic AI 기반 자동매매 시스템**으로,  
현재 문서는 **M15 구조(Agent Layer + Execution Layer + Guards/Approval)** 기준으로 업데이트되었다.

---

## 📁 프로젝트 루트

```
Trading_Agent_System/
```

---


---

## ✅ M15 핵심 구조

### Agent Layer

```
libs/agent/
 ├─ commander.py
 ├─ strategist.py
 ├─ scanner.py
 ├─ monitor.py
 ├─ reporter.py
 └─ executor.py          # Agent 레벨 Executor
```

### Execution Layer

```
libs/execution/
 └─ executor.py          # 실제 API 실행 전용
```

### Docs

```
docs/architecture/agent_layer.md
docs/architecture/execution_model.md
docs/plan/project_tree.md
docs/plan/m15_structure.md
```

## 1. 환경 / 설정

```
config/
 └─ .env.example
.env
requirements.txt
```

### 설명
- **config/.env.example**  
  실행에 필요한 환경 변수 템플릿 (API Key, Secret, Host 등)
- **.env**  
  실제 실행 환경 변수 (git ignore 대상)
- **requirements.txt**  
  Python 의존성 목록

---

## 2. 데이터 영역

```
data/
 ├─ originals/
 │  ├─ - 복사본.env
 │  └─ 키움 REST API 문서.xlsx
 └─ specs/
    ├─ kiwoom_api_list_tagged.jsonl
    ├─ kiwoom_apis.jsonl
    └─ api_catalog.jsonl
```

### 2.1 data/originals/
- **원본 자료 보관용 디렉토리**
- 시스템 런타임에서는 **직접 사용하지 않음**
- 언제든 재가공/재빌드 가능한 source 데이터

| 파일 | 설명 |
|----|----|
| 키움 REST API 문서.xlsx | 키움 공식 REST API 원본 문서 |
| 복사본.env | 과거 실험/참고용 환경 설정 |

---

### 2.2 data/specs/
- Agent 시스템이 사용하는 **정규화된 API 스펙 계층**

| 파일 | 설명 |
|----|----|
| kiwoom_api_list_tagged.jsonl | 태그/분류 중심 API 정리 |
| kiwoom_apis.jsonl | REST 호출 중심 API 정리 |
| **api_catalog.jsonl** | 단일 Canonical API Catalog |

---

## 3. 문서 (설계·계약·철학)

```
docs/
 ├─ plan/
 │  ├─ kiwoom_agentic_trader_plan.md
 │  ├─ m3_api_discovery.md
 │  ├─ m4_api_planner.md
 │  └─ m5_prepare_request.md
 ├─ agents.md
 ├─ architecture.md
 ├─ composite_skills.md
 ├─ dtos.md
 ├─ io_contracts.md
 ├─ registry.md
 ├─ runtime.md
 └─ skill_map.md
```

---

## 4. 라이브러리 (Core Logic)

```
libs/
 ├─ event_logger.py
 ├─ api_catalog.py
 ├─ api_discovery.py
 ├─ api_planner.py
 └─ api_request_builder.py
```

---

## 5. 그래프 노드

```
graphs/
 └─ nodes/
    ├─ ensure_token.py
    ├─ plan_api.py
    └─ prepare_api_call.py
```

---

## 6. 테스트

```
tests/
 ├─ test_event_logger.py
 ├─ test_api_catalog.py
 ├─ test_build_api_catalog.py
 ├─ test_api_discovery.py
 ├─ test_api_planner.py
 └─ test_api_request_builder.py
```

---

## 🔁 전체 흐름 요약

```
자연어 요청
 → (M3) API 후보 Top-K 탐색
 → (M4) 선택 or 질문
 → (M5) 요청 객체 준비
 → (M6 예정) 실제 API 호출
```

---

## ✅ 현재 상태 선언

- M1 ~ M5 완료
- 실행/주문 로직 없음
- 골격 및 계약 고정
- 파일 추가 중심 확장 구조 확립