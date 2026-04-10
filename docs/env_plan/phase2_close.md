# Phase 2 Close: Numeric Parameter Migration

## Summary
Numeric runtime parameters moved to Commander.

## Key Changes
- cooldown / hold / threshold style runtime parameters moved to `applied_policy`
- env minimized further

## Result
Commander owns operational numeric parameters.

## Validation
- Regression tests passed
- Candidate distribution unchanged

## Status
CLOSED
