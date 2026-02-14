# M3 – API Discovery (Top-K Selection)

## Purpose
Convert a natural language request into a ranked list of API candidates.

## Characteristics
- Discovery only (no execution)
- Returns Top-K candidates
- Explicit uncertainty handling

## Contract
- Input: user query
- Output: list[ApiMatch]

## Design decision
- `top_k` is part of the public contract
- Discovery does not decide
- Final selection is delegated to a planner
