# Phase 3 Close: Scanner Fallback/Source Migration

## Summary
Scanner fallback and source policy moved to Commander.

## Key Changes
- strict_only / fallback / source ownership moved
- env keys removed

## Result
Commander controls candidate generation policy.

## Validation
- fallback behavior unchanged
- candidate distribution unchanged
- tests passed

## Remaining
- heuristic tests (non-critical)
- additional scanner policies

## Status
✅ CLOSED (Ready for live validation)
