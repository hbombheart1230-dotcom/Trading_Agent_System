# M6-1 – HTTP Client (Base Layer)

## Purpose
Introduce a minimal HTTP client that supports:
- base_url joining
- timeout
- retry with backoff
- dry_run (no network)

## Guarantees
- No Kiwoom-specific auth logic in this module
- Can be unit-tested without real network calls (session injection)
