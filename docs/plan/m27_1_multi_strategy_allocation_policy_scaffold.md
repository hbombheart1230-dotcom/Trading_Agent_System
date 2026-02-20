# M27-1: Multi-Strategy Allocation Policy Scaffold

- Date: 2026-02-20
- Goal: start M27 with a deterministic portfolio allocation policy that can be validated offline.

## Scope (minimal)

1. Add allocation policy module for multiple strategy profiles.
2. Add one operator check script with pass/fail output.
3. Add regression tests for proportional split, cap enforcement, and script entrypoint.

## Implemented

- File: `libs/runtime/portfolio_allocation.py`
  - Added `allocate_portfolio_budget(...)`:
    - filters active strategy profiles (`enabled=true`, `weight>0`)
    - applies reserve ratio (`reserve_ratio`) before allocation
    - allocates notional by normalized weight
    - enforces per-strategy optional cap (`max_notional_ratio`)
    - redistributes leftover budget to non-capped strategies
  - Returns deterministic output payload:
    - `allocation_total`, `unallocated_notional`, `allocations`, `failures`

- File: `scripts/run_m27_allocation_policy_check.py`
  - Runs allocation with default profile set (`trend`, `mean_reversion`, `event_driven`)
  - Verifies:
    - `allocation_total <= allocatable_notional`
    - each strategy allocation does not exceed `max_notional`
  - Exit code:
    - `0`: pass
    - `3`: fail

- File: `tests/test_m27_1_allocation_policy.py`
  - proportional allocation regression
  - cap + redistribution regression
  - check script JSON pass regression
  - script file entrypoint import-resolution regression

## Notes for M27-2

- Next step should add intent conflict resolver over this allocation output:
  - simultaneous same-symbol opposite intents
  - concentration/exposure limit clipping at commander/supervisor boundary
