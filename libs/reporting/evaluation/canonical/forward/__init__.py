"""UEF-2A -- Canonical Forward Calculation-Recipe Contract (BOUNDARY CLOSURE).

Work Package A/Fix-series (UEF-1, now formally frozen) owns event/record/
relation identity. This package (UEF-2A) is split into two explicit layers:

    - `contracts.py` + `policy.py` -- the GENERIC FORWARD CORE. Every
      symbol here is program-name-agnostic (no Q9/Q10/Q11/Q12/Opening
      anywhere) and declares an explicit calculation RECIPE in three
      separated layers:
          A. Reference / Origin Resolution  (`ReferenceResolutionPolicy`)
          B. Checkpoint Observation Resolution  (`ObservationPolicy`)
          C. Excursion (MFE/MAE) Resolution  (`ExcursionPolicy`)
    - `profiles.py` -- the SOURCE-DERIVED SEMANTIC PROFILE layer: the 14
      real checkpoint calculators' own declarative recipes, each built
      purely by composing the generic core above. UEF-2B (not started)
      will consume a profile's `ForwardPolicy` generically; it must never
      need to know which calculator produced it.

No calculation engine lives here (that is UEF-2B), and nothing here is
wired into any existing evaluator, report, or runtime path -- importing
this package has zero effect on existing behavior. Cost/net/WR/PF/MDD are
out of scope for this whole package (UEF-3); `SourceResultCostSemantics`
only records whether a LEGACY result already carried a cost adjustment.
"""

from .contracts import (
    FORWARD_POLICY_SCHEMA_VERSION,
    DataCompletenessKind,
    EvidenceVerificationState,
    ExcursionPriceField,
    ForwardSessionResolverAuthority,
    HorizonKind,
    MfeMaeWindowEnd,
    MissingObservationStatus,
    MissingResolutionPolicy,
    ObservationSelectionMode,
    PriceCandidate,
    ReferenceResolutionKind,
    SourceResultCostSemantics,
    TradeDirection,
)
from .policy import (
    DataCompletenessPolicy,
    ExcursionPolicy,
    FixedClockSpec,
    ForwardPolicy,
    ForwardPolicyValidationError,
    ForwardSessionSpec,
    GrossReturnPolicy,
    HorizonSpec,
    ObservationPolicy,
    PriceResolutionPolicy,
    ReferenceResolutionPolicy,
    SessionCloseSpec,
    deserialize_forward_policy,
    serialize_forward_policy,
)

__all__ = [
    "FORWARD_POLICY_SCHEMA_VERSION",
    "HorizonKind",
    "ForwardSessionResolverAuthority",
    "ObservationSelectionMode",
    "MissingResolutionPolicy",
    "MissingObservationStatus",
    "EvidenceVerificationState",
    "PriceCandidate",
    "ExcursionPriceField",
    "MfeMaeWindowEnd",
    "TradeDirection",
    "ReferenceResolutionKind",
    "DataCompletenessKind",
    "SourceResultCostSemantics",
    "ForwardPolicyValidationError",
    "FixedClockSpec",
    "PriceResolutionPolicy",
    "SessionCloseSpec",
    "ForwardSessionSpec",
    "DataCompletenessPolicy",
    "ObservationPolicy",
    "ExcursionPolicy",
    "ReferenceResolutionPolicy",
    "HorizonSpec",
    "GrossReturnPolicy",
    "ForwardPolicy",
    "serialize_forward_policy",
    "deserialize_forward_policy",
]
