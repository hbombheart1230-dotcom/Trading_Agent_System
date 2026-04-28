# Kiwoom Theme Strength Packet

## 목적

전략가가 계속 `broad_market_leaders`에 머무르는 문제를 줄이기 위해 Kiwoom 테마 데이터를 별도 packet으로 정규화한다. 이 packet은 종목을 최종 선택하지 않는다. 역할은 두 가지다.

- 전략가: `available_themes`, `theme_scores`, `theme_strength_packet`을 보고 실제 Kiwoom 테마 중에서 `selected_themes`를 고른다.
- 스캐너: `selected_themes`와 `theme_map`을 이용해 `sector_theme` 후보 풀을 만들고, 그 안에서 거래대금, 거래량, 모멘텀, 추세, 감성, 메모리 bias를 합산해 종목을 고른다.

## Kiwoom Source

- `ka90001` 테마그룹별요청
- endpoint: `/api/dostk/thme`
- 주요 필드: `thema_grp_cd`, `thema_nm`, `stk_num`, `flu_rt`, `rising_stk_num`, `fall_stk_num`, `dt_prft_rt`, `main_stk`
- `ka90002` 테마구성종목요청
- endpoint: `/api/dostk/thme`
- 주요 필드: `thema_grp_cd` 기준 구성종목 목록

## Runtime Activation

운영에서는 별도 env 플래그를 기본 활성 조건으로 쓰지 않는다. Commander가 Scanner에 부여한 Kiwoom live fetch 정책을 테마 packet도 따른다.

- 기본 활성 기준: `applied_policy.scanner.kiwoom.live_fetch=true`
- 명시적 override: `theme_live_fetch` 또는 `kiwoom_theme_live_fetch`
- 구성종목 조회: 테마 live fetch가 켜지면 `ka90002`도 기본 조회한다.
- 명시적 구성종목 override: `theme_fetch_components` 또는 `kiwoom_theme_fetch_components`
- 테스트/offline: pytest 환경에서는 별도 허용 없이는 live 네트워크 호출을 막는다.

따라서 `theme_source_status=unavailable`이고 `reason=kiwoom_theme_live_fetch_disabled`라면, live 런에서 Commander-applied scanner policy가 전달되지 않았거나 theme-specific override가 꺼진 상태로 해석한다.

## Packet Schema

`libs/read/kiwoom_theme_reader.py`의 `build_theme_strength_packet()`은 아래 형태를 반환한다.

```json
{
  "schema_version": "kiwoom_theme_strength.v1",
  "source": "state_mock|env_mock|kiwoom_live|unavailable",
  "status": "ok|empty|unavailable",
  "reason": "source detail",
  "top_themes": [],
  "theme_scores": {},
  "theme_map": {},
  "component_symbols_by_theme": {},
  "component_source": "",
  "formula": {
    "period_return": 0.35,
    "change_rate": 0.25,
    "breadth": 0.25,
    "component_strength": 0.15
  }
}
```

## Scoring

테마 점수는 deterministic score다. LLM이 임의로 만든 테마명을 tradable universe로 쓰지 않고, Kiwoom 데이터 기반 가중치로 후보 테마를 정렬한다.

- `period_return`: `dt_prft_rt / 30`
- `change_rate`: `flu_rt / 10`
- `breadth`: `(rising_stk_num - fall_stk_num) / stk_num`
- `component_strength`: 구성종목 평균 등락률/기간수익률
- 최종 score: `0.35*period_return + 0.25*change_rate + 0.25*breadth + 0.15*component_strength`
- 최종 score는 `-1.0 ~ 1.0` 범위로 제한한다.

## Runtime Handoff

전략가 출력은 아래 필드를 포함해야 한다.

- `theme_strength_packet`
- `theme_source`
- `theme_source_status`
- `theme_source_reason`
- `theme_source_fallback_used`
- `available_themes`
- `selected_themes`
- `theme_strategy`

스캐너는 같은 packet 요약을 raw input과 `scanner_output`에 남긴다. 이로써 “테마가 왜 broad_market_leaders로 남았는지”와 “Kiwoom 테마가 실제 sector_theme 후보 생성에 쓰였는지”를 artifact에서 분리해서 확인할 수 있다.

## Report Visibility

리포트 검수에서는 `theme_source_status`를 먼저 본다.

- `ok`: Kiwoom 또는 mock 테마 강도 packet이 전략가/스캐너 판단에 사용됐다. `top_themes`, `selected_themes`, `theme_scores`, `theme_boost`, `sector_theme` 후보 수를 같이 확인한다.
- `empty`: live 조회는 수행됐지만 Kiwoom 응답에서 사용 가능한 테마 row가 없었다.
- `unavailable`: 테마 packet 경로는 호출됐지만 실제 테마 강도 데이터가 없었다. 이 경우 전략가는 기존 `broad_market_leaders` 같은 fallback 프레임에 머무를 수 있고, 스캐너의 `theme_boost`는 0으로 남는 것이 정상이다.

AI trade report에는 다음 항목이 보여야 한다.

- 시장/전략가 섹션: `theme_source`, `theme_source_status`, `theme_source_reason`, `theme_strength_top_themes`, `selected_themes`
- 종목 선정 섹션: `selected_sources`에 `sector_theme` 포함 여부, `theme_boost`, `sector_theme_count`
- canonical strategist artifact: 동일 필드를 최상위 또는 `decision_frame` 쪽에 보관한다.
