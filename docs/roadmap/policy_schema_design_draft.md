# Policy Schema Design — Producer Interpretation Policy Draft

## 1. 목적

현재 Monitor는 `entry_policy_contract.selected_policy`를 explicit policy consumer 경로로 읽을 수 있도록 준비되어 있다.  
하지만 실제 producer 쪽 policy payload는 여전히 숫자형 threshold 중심이어서, runtime에서는 `fallback_playbook` 해석 비중이 높다.

이 문서의 목적은 다음과 같다.

- Strategist / Commander가 생성하는 policy를 **해석 가능한 policy object**로 고정
- Monitor가 threshold dict가 아니라 **interpretation policy**를 우선 읽도록 하는 producer contract 초안 정의
- 숫자형 threshold policy는 즉시 제거하지 않고 **fallback safety layer**로 유지
- 이후 5-4 wiring / ownership 설계의 기준선 제공

---

## 2. 배경

현재 runtime 관찰 결과는 다음을 보여준다.

- `selected_source`는 대부분 `commander_applied_policy`
- `selected_policy`는 주로 숫자형 threshold key를 담음
- `policy_schema_available=false`가 대부분
- `interpretation_basis=fallback_playbook`가 대부분

즉 Monitor는 explicit policy consumer가 될 준비는 되어 있지만, producer가 아직 **해석 가능한 explicit interpretation policy**를 거의 공급하지 않는다.

이 상태에서는:

- policy-aware monitor foundation은 존재
- 하지만 실전 해석은 여전히 playbook fallback 비중이 큼
- threshold 중심 payload와 policy-driven 구조가 동시에 존재

따라서 producer side policy shape를 명시적으로 올릴 필요가 있다.

---

## 3. 설계 원칙

### 3.1 해석 정책과 수치 정책을 분리한다

`selected_policy`는 다음 두 층을 함께 담는다.

- `interpretation_policy`
- `threshold_policy`

의도:

- `interpretation_policy`는 Monitor가 **무엇을 중요하게 해석해야 하는지**를 전달
- `threshold_policy`는 기존 numeric fallback / safety / legacy gate 지원용으로 유지

### 3.2 additive only

- 기존 top-level threshold key는 당분간 유지
- `threshold_policy`를 병렬 추가
- `interpretation_policy`를 새로 추가
- 기존 consumer를 깨지 않음

### 3.3 deterministic producer-first

- 초기는 LLM 해석이 아니라 deterministic mapping으로 시작
- playbook / regime / defensive/aggressive frame을 기반으로 producer가 interpretation field 생성
- Monitor는 이 field를 소비하고, 없을 때만 fallback

### 3.4 threshold는 fallback safety로 내린다

장기적으로는 policy-driven decision 비중이 커져야 하지만, 현재 단계에서는:

- final BUY/WAIT owner는 legacy gate 유지
- numeric threshold policy는 safety / fallback 역할 유지
- interpretation policy는 점진적으로 상위 의미를 제공

---

## 4. 목표 shape

### 4.1 canonical selected_policy shape

```python
selected_policy = {
    "interpretation_policy": {
        "entry_style": str | None,
        "required_checks": list[str],
        "preferred_checks": list[str],
        "relaxable_checks": list[str],
        "blockers": list[str],
        "priority_hints": {
            "reclaim": str | None,
            "volume": str | None,
            "breakout": str | None,
            "pullback": str | None,
        },
        "evidence_focus": {
            "primary": list[str],
            "secondary": list[str],
        },
        "notes": list[str],
        "policy_adjustments": list[dict] | list[str],
    },
    "threshold_policy": {
        # 기존 reclaim / volume / extension 등 numeric fallback policy
    },

    # backward compatibility
    # 기존 top-level threshold keys 유지
}
```

---

## 5. interpretation_policy 필드 의미

### 5.1 entry_style
의미:
- 현재 진입 철학의 대표 스타일
- 예: `breakout`, `pullback`, `defensive`, `reclaim`, `continuation`

용도:
- Monitor가 구조적 진입 유형을 우선 이해할 수 있게 함
- playbook fallback보다 우선

### 5.2 required_checks
의미:
- 현재 정책상 반드시 만족해야 하는 체크
- 완화 대상 아님

예:
- `volume_ok`
- `breakout_ok`
- `structure_ok`

주의:
- 현재 존재하는 evidence/check 이름과 최대한 정합성 유지
- 새로운 체크 이름을 과도하게 만들지 않음

### 5.3 preferred_checks
의미:
- 만족되면 더 좋은 보조 체크
- 현재 단계에서는 설명/정렬/품질 강화용

예:
- `reclaim_ok`
- `pullback_ok`

### 5.4 relaxable_checks
의미:
- 정책상 narrow 조건에서 완화 가능성이 있는 체크

예:
- `reclaim_gate_ok`

주의:
- 곧바로 다수 gate 완화로 이어지지 않음
- 현재는 narrow policy-aware gating 또는 future gating input

### 5.5 blockers
의미:
- 절대 들어가면 안 되는 상황 또는 진입 중단 사유

예:
- `too_extended`
- `low_confidence`
- `structure_break`

주의:
- 가능하면 현재 evidence/derived naming과 연결 가능해야 함

### 5.6 priority_hints
의미:
- 어떤 신호 축을 더 중요하게 읽어야 하는지에 대한 우선순위 힌트

예:
- `reclaim: "secondary"`
- `volume: "primary"`
- `breakout: "primary"`
- `pullback: "secondary"`

주의:
- 이 값 자체가 final decision이 되면 안 됨
- interpretation / trace / summary의 입력

### 5.7 evidence_focus
의미:
- Monitor가 우선 읽어야 하는 evidence 축

예:
- `primary = ["breakout_ok", "volume_ok"]`
- `secondary = ["reclaim_ok"]`

용도:
- policy_interpreter_trace / policy_alignment_summary의 정렬 기준

### 5.8 notes
의미:
- 짧은 정책 메모
- prose가 아니라 짧은 설명 리스트

예:
- `"breakout continuation preferred"`
- `"reclaim may be relaxed if near-ready"`

### 5.9 policy_adjustments
의미:
- producer가 정책상 가한 조정 정보
- 현재는 lightweight metadata
- future audit/provenance 확장 가능

---

## 6. threshold_policy 의미

`threshold_policy`는 기존 numeric threshold policy를 담는다.

역할:

- legacy gate의 fallback 입력
- explicit interpretation policy가 비어 있을 때도 시스템 유지
- safety boundary / conservative runtime 유지
- gradual migration 동안 backward compatibility 제공

중요:
- interpretation policy가 생겼다고 threshold policy를 즉시 제거하지 않음
- 장기적으로는 final owner가 아니라 fallback safety 역할로 내려감

---

## 7. producer 책임 분리

### 7.1 Strategist
책임:
- market/playbook/regime 기반 interpretation policy 생성
- threshold policy도 함께 생성 가능
- 초기에는 deterministic mapping으로 충분

예:
- playbook = `breakout` → `entry_style="breakout"`
- defensive frame → `required_checks` 강화
- reclaim 완화 가능 → `relaxable_checks`에 반영

### 7.2 Commander
책임:
- strategist policy를 apply/confirm
- selected source / selected policy provenance 고정
- selected_policy 안의 `interpretation_policy`를 제거하지 않고 유지

### 7.3 Monitor
책임:
- `entry_policy_contract.selected_policy`를 소비
- `interpretation_policy`를 우선 읽음
- 없을 때만 playbook fallback
- threshold policy는 legacy gate / fallback 안전장치로 사용

---

## 8. compatibility 원칙

### 8.1 explicit preferred, not mandatory
- `interpretation_policy`가 있으면 우선 사용
- 없으면 playbook fallback 유지

### 8.2 기존 top-level threshold 유지
- 기존 consumer 호환 유지
- migration 기간 동안 중복 허용

### 8.3 semantic expansion 금지
- field 의미는 현재 Monitor evidence/check naming과 정합성 유지
- 과도한 pattern ontology를 한 번에 넣지 않음

---

## 9. runtime 기대 변화

이 schema가 실제 producer에 들어가면 다음 변화가 기대된다.

### 현재
- `policy_schema_available=false` 비중 높음
- `interpretation_basis=fallback_playbook` 비중 높음

### 이후 기대
- `policy_schema_available=true` 증가
- `interpretation_basis=explicit_policy` 또는 `mixed` 증가
- Monitor가 playbook 이름이 아니라 selected_policy의 explicit field를 더 많이 소비

중요:
- 이 단계에서도 trading decision을 대폭 바꾸지 않음
- 먼저 해석 입력을 명확하게 만드는 것이 목표

---

## 10. non-goals

이번 설계 초안에서 하지 않는 것:

- final BUY/WAIT ownership migration
- broad multi-gate relaxation
- threshold 제거 또는 rewrite
- required check bypass
- chart structure feature 실제 구현
- LLM 기반 free-form policy generation
- execution path 변경

---

## 11. natural next steps

### 11.1 5-3-2
- chart structure feature vocabulary 정의
- interpretation policy와 연결 가능한 structure feature catalog 정리

### 11.2 5-4
- policy producer → policy consumer wiring 정리
- legacy gate를 fallback safety로 내리는 ownership 설계

### 11.3 env/config
- scoring/shadow env rename/deprecate 설계
- policy-driven architecture 기준으로 config surface 정리

---

## 12. 한 줄 정리

`selected_policy`를 **interpretation_policy + threshold_policy** 구조로 분리함으로써,  
Monitor가 단순 numeric threshold consumer가 아니라 **명시적 policy consumer**로 이동할 수 있는 producer-side contract 기준선을 제공한다.
