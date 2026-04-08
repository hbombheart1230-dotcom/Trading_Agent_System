from __future__ import annotations

from pathlib import Path


DOC_EXPECTATIONS = {
    "docs/execution_plan/phase_5_4_closeout.md": [
        "Phase 5-4 Closeout",
        "runtime semantics unchanged",
        "route provenance",
        "canonical artifact",
        "remaining limitations",
    ],
    "docs/execution_plan/phase_6_1_closeout.md": [
        "Phase 6-1 Closeout",
        "fact/narrative separation",
        "runtime semantics unchanged",
        "narrative axis",
        "remaining limitations",
    ],
    "docs/execution_plan/phase_6_2_closeout.md": [
        "Phase 6-2 Closeout",
        "route source",
        "fallback policy",
        "freshness",
        "runtime semantics unchanged",
    ],
    "docs/execution_plan/final_alignment_review_phase_5_4_to_6_2.md": [
        "Final Alignment Review",
        "operational baseline",
        "trade_explain",
        "freshness",
        "narrative axis",
    ],
}


def test_execution_plan_closeout_docs_are_utf8_and_have_current_keywords() -> None:
    for rel_path, keywords in DOC_EXPECTATIONS.items():
        path = Path(rel_path)
        text = path.read_text(encoding="utf-8")
        text_lower = text.lower()
        assert text.strip(), rel_path
        for keyword in keywords:
            assert keyword.lower() in text_lower, f"{rel_path} missing {keyword!r}"
