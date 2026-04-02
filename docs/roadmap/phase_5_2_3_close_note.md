# Phase 5-2-3 Close Note

## Purpose
This note freezes the current contract and responsibility boundary for the
`5-2-3` recent-window strategist feedback slice.

The purpose of `5-2-3` is not to generate richer prose by itself.
It is to expose reporting artifacts as strategist-readable, non-UI read-model
surfaces that can be reused later.

This slice specifically closes the recent-window feedback exposure chain.
It should be read as a contract/boundary note, not as a runtime integration
note.

## Background
The system already had multiple reporting artifacts:
- trade story input
- lifecycle bundle
- linked trade report
- operator brief
- daily and symbol reporting artifacts

What was missing was a stable, non-UI surface that a strategist-facing or
reporting-side consumer could read without depending on UI modules or directly
walking raw artifact trees each time.

This slice was created to solve that narrow problem.
It does **not** create a new source of truth.
It reuses existing trade story / lifecycle / bundle / linked artifact data and
exposes them in a compact, reusable form.

## Layer Chain
The current recent-window chain has four layers.

### 1. Raw window builder
- `build_recent_strategist_feedback_window(...)`
- Responsibility:
  aggregate already-normalized strategist feedback rows into a compact recent
  window payload.

### 2. Trade wrapper
- `build_recent_trade_feedback_summary_input(...)`
- Responsibility:
  adapt collected trade-level feedback inputs into the raw window builder.

### 3. Pack wrapper
- `build_trade_report_recent_feedback_pack(...)`
- Responsibility:
  wrap the compact window payload in a stable pack contract with metadata.

### 4. Meta/payload adapter
- `load_trade_report_recent_feedback_pack(meta, payloads, default_window_size=10)`
- Responsibility:
  provide a non-UI consumer entrypoint that reads the usual `meta` / `payloads`
  shape and returns the pack form directly.

## Canonical Non-UI Entry Point
For the current slice, the preferred non-UI consumer entrypoint is:

- `load_trade_report_recent_feedback_pack(...)`

This function is the most convenient boundary for later reporting-side reuse,
because it accepts existing reporting read-model input shapes rather than raw
feedback lists only.

## Contract Definition
Current pack contract:

- `schema_version`: `strategist_feedback_recent_window_pack.v1`
- `payload_type`: `recent_strategist_feedback_window`
- `available`: boolean flag meaning whether the wrapped window contains at
  least one considered trade
- `window`: the existing compact recent-window payload

### Available Flag Meaning
- `available = true`
  means `window.trades_considered > 0`
- `available = false`
  means the payload is still valid, but represents an empty or unavailable
  recent-window view

### Window Field Meaning
`window` contains the existing compact payload produced by the recent-window
builder.
This slice does not reinterpret or rename that payload.
It only exposes it in a pack form.

### v1 Scope
`strategist_feedback_recent_window_pack.v1` is a v1 exposure contract for the
existing compact payload.
It is **not** a recommendation layer, a scoring layer, or a semantic summary
layer.

## Source Of Truth: Generation vs Exposure
This slice does not generate a new truth layer.
It separates existing truth generation from read-model exposure.

### Generation layer
Existing reporting artifacts remain the source of truth:
- trade story input
- lifecycle bundle
- linked trade report
- operator brief
- related reporting artifacts already produced elsewhere

### Exposure layer
This slice only exposes existing truth in strategist-readable shapes:
- normalized strategist feedback input
- recent-window compact payload
- pack wrapper
- meta/payload adapter

In short:
- existing reporting artifacts generate truth
- `5-2-3` recent-window helpers expose that truth for non-UI consumers

## Responsibility Boundary
This slice is intentionally narrow.
It is an exposure layer only.

### Done in this slice
- trade-level strategist feedback exists in reporting artifacts
- recent-window compact payload exists
- pack wrapper exists
- meta/payload adapter exists
- non-UI consumers can read the pack without UI dependency

### Not done in this slice
- strategist runtime wiring
- strategist recommendation or bias application
- time-bucketed aggregation
- daily aggregate completion
- symbol-level expansion beyond the already completed reporting fixes
- prose or LLM summary generation
- UI consumer changes
- policy ownership changes

## Stability Rules
The current v1 contract should be treated as frozen.

Rules:
- additive changes only
- no breaking change to existing return meaning
- no semantic reinterpretation of existing fields
- if a larger structure change is needed later, introduce a parallel future v2
  instead of mutating v1 behavior in place

## Natural Next Steps
These are natural follow-ups, but they are **not** implemented in this slice.

- strategist runtime wiring
- time-bucketed pack format
- daily / symbol consumer connection on top of this contract
- later-stage recommendation / summary layering

## Practical Read
`5-2-3` recent-window strategist feedback is now at a usable baseline for
non-UI reporting consumers.

What is frozen here is not a final strategist behavior layer.
What is frozen here is a read-model contract that safely exposes already-built
reporting truth in a reusable form.
