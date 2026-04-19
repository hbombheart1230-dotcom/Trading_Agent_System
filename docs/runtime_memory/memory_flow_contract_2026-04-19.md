# Memory Flow Contract (2026-04-19)

## Goal

This contract fixes the runtime flow that connects:

- market memory
- symbol memory
- position refresh memory
- strategist, scanner, and monitor responsibilities

It exists to prevent the memory system from drifting into duplicated LLM passes or scanner re-entry loops.

## Core Runtime Flow

### 1. Strategist Pass 1

Consumer:

- `graphs/nodes/strategist_node.py`

Input:

- broad market memory only
- `reports/performance/<day>/strategy_memory.json`
- compact market context
- news / global sentiment
- candidate hints that are not final symbol commitments

Role:

- choose a broad playbook
- set risk tone
- emit initial `monitor_entry_policy`
- define scanner-facing constraints

Must not do:

- final symbol selection
- symbol-specific historical reasoning that depends on a selected symbol

## 2. Scanner Deterministic Ranking

Consumer:

- `graphs/nodes/scanner_node.py`

Input:

- strategist pass 1 output
- candidate universe
- deterministic symbol memory priors from `reports/symbols/<SYMBOL>/symbol_memory.json`

Role:

- rank candidates
- apply deterministic bonuses / penalties
- select the final symbol

Must not do:

- scanner LLM reframe
- second broad strategy pass

## 3. Monitor Execution

Consumer:

- `graphs/nodes/monitor_node.py`

Input:

- selected symbol
- inherited strategist/scanner policy
- runtime monitor state

Role:

- execute entry / hold / exit logic
- surface stagnation, blockers, and active exit context

Must not do:

- become a new LLM consumer
- run its own strategic reasoning pass

## 4. Strategist Pass 2 Refresh

Consumer:

- `graphs/nodes/strategist_node.py`

Trigger:

- selected-symbol reframe when explicitly needed
- long-hold / repeated-hold position refresh

Input:

- position refresh packet
- selected symbol memory excerpt
- current monitor policy summary
- current hold / blocker / exit-axis state

Role:

- tune policy for the already selected symbol or open position
- emit `policy_adjustment`
- emit `strategy_adjustment_directives` as artifact-only strategic action surface
- keep or change baseline with explicit rationale

Must not do:

- re-run scanner
- choose a new symbol

Current execution rule:

- `monitor_entry_policy` remains the only downstream execution contract
- `strategy_adjustment_directives` is currently artifact-only and is not consumed by scanner or monitor runtime logic

## 5. Post-Trade Feedback

Consumers:

- trade report generation
- retrospective strategist feedback adapters
- future market-memory updates

Primary surfaces:

- `libs/reporting/trade_read_model.py`
- `libs/reporting/strategy_read_model.py`
- `reports/trades/*`
- `reports/dev/analysis/reporter_analysis/*`

Role:

- explain outcomes
- compress recurring failures and route mix
- feed the next market-memory build

## Ordering Rules

1. market memory may influence strategist pass 1 only
2. symbol memory may influence scanner deterministically before symbol selection
3. symbol memory may influence strategist only after symbol selection or during position refresh
4. monitor consumes policy; it does not create a new strategy layer
5. strategist pass 2 refresh tunes policy; it does not trigger scanner re-selection

## Anti-Patterns

The following are disallowed:

1. scanner LLM as a new parallel owner
2. monitor LLM as a new policy owner
3. re-running scanner after strategist pass 2 refresh
4. feeding symbol-history prose into strategist pass 1 as if a symbol were already chosen
5. creating new memory roots when an existing canonical surface already exists

## Current Canonical Paths

- market memory:
  - `reports/performance/<day>/strategy_memory.json`

- symbol memory:
  - `reports/symbols/<SYMBOL>/symbol_memory.json`

- position refresh:
  - runtime packet only, sourced from open-position state plus symbol-memory excerpt

## Design Rule

If a proposed change introduces another LLM pass or another report surface, it must answer:

1. why an existing owner cannot absorb it
2. what explicit consumer will read it
3. why the current memory-flow ordering is insufficient

If those answers are weak, the change should not be added.
