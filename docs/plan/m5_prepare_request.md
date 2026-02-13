# M5 – Prepare API Request (No Execution)

## Purpose
Build a structured request object from:
- Selected API (from M4)
- Runtime context (known values)

## Outputs
- ready: `PreparedRequest` (method/path/query/body/headers)
- ask: question + missing required fields

## Guarantees
- No HTTP calls
- No side effects
- Deterministic preparation logic
