import sys
import types

import libs.reporting.live_execution_bundle_runner as _runner
from libs.reporting.trade_bundle_assembly import derive_trade_recovery_metadata as _shared_derive_trade_recovery_metadata

globals().update({name: getattr(_runner, name) for name in dir(_runner) if not name.startswith("__")})


def _seed_diagnostics_for_policy(*args, **kwargs):
    out = _runner._seed_diagnostics_for_policy(*args, **kwargs)
    if isinstance(out, dict) and "diagnostics" in out and "should_attempt_generation" in out:
        return out["diagnostics"], bool(out["should_attempt_generation"])
    return out


def _derive_trade_recovery_metadata(*, lifecycle, evidence_completeness, section_provenance):
    return _shared_derive_trade_recovery_metadata(
        lifecycle=lifecycle,
        evidence_completeness=evidence_completeness,
        section_provenance=section_provenance,
        has_substantive_entry_evidence_fn=_runner._has_substantive_entry_evidence,
    )


class _RunnerMirrorModule(types.ModuleType):
    """Keep test/runtime patch points on this thin wrapper aligned with runner globals."""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if hasattr(_runner, name):
            setattr(_runner, name, value)


sys.modules[__name__].__class__ = _RunnerMirrorModule


if __name__ == "__main__":
    raise SystemExit(main())
