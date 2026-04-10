# Phase 5 Catalog Review

## Purpose
Phase 5 introduces a structured model catalog layer without affecting runtime
behavior.

This layer is intentionally data-only for now:
- no Commander integration yet
- no Strategist or Reporter runtime reads
- no auto model switching

## Current Structure

### Raw OpenRouter snapshot
- path: `data/model_catalog/openrouter_models.json`
- source: `https://openrouter.ai/api/v1/models`
- role: keeps the upstream payload as a local snapshot for later review and
  transformation

### Generated internal cards
- path: `data/model_catalog/model_cards.json`
- role: normalized, lighter-weight model metadata for internal lookup and later
  planning

## model_cards schema
Each card currently includes:
- `model_id`
- `provider`
- `tags`
- `context_window`
- `cost_tier`
- `latency_tier`
- `reliability`
- `supports_json`
- `prompt_cost`
- `completion_cost`
- `display_name`
- `recommended_roles`
- `strengths`
- `weaknesses`
- `json_stability_note`
- `latency_note`
- `cost_note`
- `long_context_note`

## Manual quality cards added first
This phase only enriches a few currently relevant models by hand.

### `minimax/minimax-m2.5`
- tags: `cheap`, `fast`, `json_stable`
- intended use: lightweight intraday/reporting surfaces
- note: good low-cost baseline, not the strongest deep reasoning option

### `deepseek/deepseek-v3.2`
- tags: `cheap`, `json_stable`, `report_quality`
- intended use: balanced strategist/general reasoning surfaces
- note: balanced operational default when cost and quality both matter

### `moonshotai/kimi-k2.5`
- tags: `reasoning`, `long_context`, `report_quality`, `json_stable`
- intended use: daily/deeper review surfaces
- note: stronger high-context review option, but not the cheapest intraday path

## Runtime connection status
Phase 5 remains intentionally unconnected from runtime:
- Commander does not read model cards yet
- Strategist does not read model cards yet
- Reporter does not read model cards yet
- execution profile / routing behavior remains unchanged

## Expected Phase 6 direction
Phase 6 can use this catalog as a planning surface for:
- profile review and curation
- better metadata-backed model selection policy
- future advisory-only catalog visibility in reports or policy review

That future phase should still be careful to separate:
- catalog metadata
- Commander policy
- actual runtime switching behavior
