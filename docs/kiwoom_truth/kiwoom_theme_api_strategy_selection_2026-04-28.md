# Kiwoom Theme API Strategy Selection

## Purpose

Kiwoom theme data should be treated as the primary truth for theme selection.
The Strategist must not invent a tradable theme universe when Kiwoom exposes a live theme list.
The Strategist selects themes, not symbols. The Scanner ranks symbols inside the selected theme universe.

## Runtime Flow

```text
Kiwoom ka90001 theme groups
-> Kiwoom ka90002 theme components
-> deterministic theme strength packet
-> Strategist selected_themes / avoided_themes / theme_strategy
-> Scanner sector_theme universe
-> Scanner symbol ranking
-> Commander / Monitor execution controls
```

## Runtime Activation

Theme fetch activation follows the same Commander-owned Kiwoom runtime policy used by the Scanner.
Do not require a separate env flag for normal live operation.

- Primary switch: `applied_policy.scanner.kiwoom.live_fetch`
- Commander-first handoff: runtime must attach `applied_policy` before invoking Strategist, including the first fresh strategy frame and post-scanner refresh.
- Explicit opt-out/override: `theme_live_fetch` or `kiwoom_theme_live_fetch` in state/policy
- Component fetch: enabled by default when theme live fetch is enabled, unless `theme_fetch_components=false` or `kiwoom_theme_fetch_components=false`
- Test/offline guard: pytest still blocks live network fetch unless explicitly allowed by the test

This keeps runtime control under Commander while allowing a theme-specific kill switch.

## API Role

- `ka90001`: provides the available Kiwoom theme list and theme-level strength inputs.
- `ka90002`: provides component symbols for each selected or top-ranked theme.
- `theme_strength_packet`: carries the normalized runtime packet.
- `available_themes`: compact Strategist input derived from the Kiwoom packet.
- `selected_themes`: Strategist-selected tradable themes, constrained to `available_themes` when Kiwoom data is available.

## Agent Boundaries

- Strategist:
  - reads `available_themes`, market state, news, memory, commander posture, and theme strength.
  - selects `selected_themes` and `avoid_themes`.
  - assigns a playbook overlay and scanner directive for selected themes.
  - does not select the final symbol.
- Scanner:
  - uses `selected_themes` first when building the `sector_theme` candidate universe.
  - ranks component symbols using trading value, volume, momentum, trend, sentiment, memory bias, and compatibility signals.
  - may keep a commander-controlled fallback slot when selected themes are weak or empty.
- Commander:
  - controls aggressiveness, fallback breadth, source expansion, and whether low-confidence theme selection should be narrowed or widened.
- Monitor:
  - decides whether the selected symbol is tradable now.

## Selection Rules

When `theme_source_status=ok`:

- `selected_themes` should be chosen from Kiwoom `available_themes`.
- LLM-created abstract labels such as `broad_market_leaders` can be used only as interpretation or fallback labels, not as primary tradable theme universe labels.
- Scanner `sector_theme` candidates should come from Kiwoom component symbols whenever component data exists.
- Reports must show the chain: Kiwoom available themes -> Strategist selected themes -> Scanner sector_theme count -> selected symbol.

When `theme_source_status=unavailable`:

- `selected_themes` must stay empty because no tradable Kiwoom theme universe was confirmed.
- Broad labels such as `broad_market_leaders` may be carried only in `themes_hint` / `fallback_theme_hints` for context.
- Scanner should clearly mark `theme_filter_reason` / `theme_source_reason`.
- Reports must distinguish "Kiwoom theme unavailable" from "Strategist deliberately chose broad-market leaders."

## Patch Contract

Additive fields:

```json
{
  "available_themes": [
    {
      "theme": "string",
      "theme_code": "string",
      "score": 0.0,
      "component_count": 0,
      "component_symbols": ["005930"]
    }
  ],
  "selected_themes": ["string"],
  "theme_strategy": {
    "source": "kiwoom_theme_strength_packet",
    "selection_mode": "kiwoom_api_constrained|fallback",
    "selected_themes": [
      {
        "theme": "string",
        "score": 0.0,
        "playbook_overlay": "momentum|pullback|defensive|fallback",
        "scanner_directive": "string",
        "reason": "string"
      }
    ],
    "fallback_used": false,
    "fallback_reason": ""
  }
}
```

Scanner should prefer `selected_themes` over generic `themes` when present.
This keeps the old theme fields backward-compatible while making Kiwoom API theme selection explicit.
