# Live Trading Validation Checklist

## Pre-Market
- system starts clean
- policy injection verified
- latest runtime patch state understood

## Intraday
- scanner candidates exist
- fallback behavior correct
- route distribution normal
- strategist calls stable
- report subprocess count stays controlled

## Post-Market
- reports generated where expected
- feedback packet present where expected
- anomalies logged
- follow-up hotfix candidates written down

## Critical Checks
- no-trade anomalies
- overtrading signals
- missing candidates
- unexpected helper subprocess growth
- artifact/source-of-truth mismatches

## Rule
Do not make broad structural changes during market hours.

## Allowed intraday exceptions
Small, safety-oriented changes are allowed when they are clearly scoped and reversible.

Examples:
- stopping runaway helper subprocesses
- disabling noisy non-critical report generation
- patching artifact/observability mismatches that affect incident understanding
- tightening final guard behavior that prevents clearly unwanted execution paths

## Intraday patch standard
If an intraday patch is necessary, keep it:
- additive where possible
- narrowly scoped
- easy to validate quickly
- clearly documented as runtime hotfix work, not phase progress
