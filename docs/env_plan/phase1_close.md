# Phase 1 Close: Toggle Ownership Migration

## Summary
All behavioral toggles moved from env to Commander.

## Key Changes
- `*_ENABLED` / `*_STRICT` style behavior toggles removed from env
- `applied_policy` introduced as canonical source

## Result
Commander owns all behavior toggles.

## Validation
- Tests passed
- No trading semantics change

## Status
CLOSED
