# UEF Freeze Manifest -- SHA256 Baseline Integrity

**This is the one authoritative freeze manifest for UEF-1 / UEF-2A / UEF-2B / UEF-3A / UEF-3B / UEF-3C.**
Do not create a second manifest file elsewhere; if this file's location
changes, update `scripts/verify_uef_freeze_manifest.py`'s `MANIFEST_PATH`
in the same change.

## Provenance rule (read before trusting this file)

The hashes below are declared as the **integrity baseline authority
starting 2026-09-14** for the original 6 UEF-1/UEF-2A/UEF-2B rows,
**starting 2026-09-15** for the 3 UEF-3A rows added when UEF-3A reached
its own independent-audit formal freeze (CRITICAL:0 HIGH:0 MEDIUM:0 LOW:0,
FORMAL FREEZE: YES), **starting 2026-09-15** for the 1 UEF-3B row added
when UEF-3B reached its own independent-audit formal freeze (CRITICAL:0
HIGH:0 MEDIUM:0 LOW:0, APPROVE_UEF3B, FORMAL FREEZE: YES, after its own
FIX1 MDD-determinism closure), and **starting 2026-09-15** for the 1
UEF-3C row added when UEF-3C reached its own independent-audit formal
freeze (CRITICAL:0 HIGH:0 MEDIUM:0 LOW:0, FORMAL FREEZE: YES, after its
own FIX1 policy-provenance/member-state closure). No date is a
retroactive claim that these exact byte sequences existed at any earlier
"formally frozen" announcement -- each stage's announcement predates its
own manifest entry and no prior hash snapshot was ever recorded for it,
so no such claim can be made truthfully. From each entry's own start date
forward, any change to that listed file's bytes is detectable by
re-running the verifier below and will show as `MISMATCH`; that is the
only integrity claim this manifest makes.

## How to verify

```bash
python scripts/verify_uef_freeze_manifest.py
```

Exits `0` with `MISMATCH: 0` when every listed file's current SHA256
matches this manifest; exits non-zero and prints each mismatched path
otherwise. The verifier is read-only -- it never modifies a file or this
manifest, even on mismatch.

## Scope

Tracked here: the canonical identity/contract/policy/profile/engine
source files that define UEF-1's identity contract, UEF-2A's frozen
forward-semantics contract (generic core + the 14 source-derived
profiles), UEF-2B's generic forward engine, UEF-3A's canonical
cost/metric contract (vocabulary + policy/record shapes + package
re-exports), UEF-3B's canonical cost/metric calculation engine, and
UEF-3C's canonical aggregation pipeline. **Not** tracked: test fixtures,
generated reports, runtime state, or any other repository file -- this
manifest protects frozen *semantic authority* source files only.

## Manifest

| relative_path | freeze_stage | freeze_date | sha256 |
|---|---|---|---|
| libs/reporting/evaluation/canonical/contracts.py | UEF-1 | 2026-09-14 | 8b98fc970dd9fbb37611a2d2988f3c5265ad1d7fd3432903ba599317ed8bc3d0 |
| libs/reporting/evaluation/canonical/identity.py | UEF-1 | 2026-09-14 | 24c9fe815608c654b7ab848924afd287651577823733dbc1e88c0c7d5edfda27 |
| libs/reporting/evaluation/canonical/forward/contracts.py | UEF-2A | 2026-09-14 | 0f716a572aaccc07544446a4dbabf46f871ef20142730f10d527c5ff6dba23a5 |
| libs/reporting/evaluation/canonical/forward/policy.py | UEF-2A | 2026-09-14 | 36daf50365861cead3a2d1b7ad318f97de9ef51349a8ead8e6d2a5f61308ee4b |
| libs/reporting/evaluation/canonical/forward/profiles.py | UEF-2A | 2026-09-14 | ee6551d1b97f90ce19153e762b9ce98b4fc048d7eea63bb286189d347165730b |
| libs/reporting/evaluation/canonical/forward/engine.py | UEF-2B | 2026-09-14 | a2d2a8e9e845f8334762e6e002bfc0201e27420aaf0ebf23e39632f71a6f49b1 |
| libs/reporting/evaluation/canonical/metrics/contracts.py | UEF-3A | 2026-09-15 | 3e43807b41fc92d8b5c4c6978747603d69362dd412054016bd252d0bcc0b1dea |
| libs/reporting/evaluation/canonical/metrics/policy.py | UEF-3A | 2026-09-15 | 837b566df38f8b7b9b1d3c52956b651409e9394a7eb262eb38400ecd3c403a6d |
| libs/reporting/evaluation/canonical/metrics/__init__.py | UEF-3A | 2026-09-15 | 221adf9a503cc24398d7beb4f12351811bd3b8ac104b2ca5c8391d39f34a2597 |
| libs/reporting/evaluation/canonical/metrics/engine.py | UEF-3B | 2026-09-15 | b198f767c665b7e38ee6916a534ef8b92923a304d91fea7b08f422037a155dbc |
| libs/reporting/evaluation/canonical/metrics/aggregation.py | UEF-3C | 2026-09-15 | e2d1ab67c4160ffafa34a2a4c169bcafc9840cb2e19e9737f911bf43cede173b |

## Updating this manifest

This manifest must only be regenerated when a NEW formal freeze/re-freeze
of UEF-1, UEF-2A, UEF-2B, UEF-3A, UEF-3B, or UEF-3C is explicitly declared
(e.g. an approved amendment after a documented `UEF2A_FREEZE_CONFLICT`/
`UEF2B_ARCHITECTURE_BLOCKER`/`UEF3A_FIX2_SCOPE_FAILURE`/
`UEF3B_FROZEN_CONTRACT_CONFLICT`/`UEF3C_FROZEN_CONTRACT_CONFLICT`
resolution) -- never silently alongside an unrelated change. A
regeneration must update `freeze_date` for the affected row(s) and should
note, in the surrounding prose, why the prior baseline no longer applies.
