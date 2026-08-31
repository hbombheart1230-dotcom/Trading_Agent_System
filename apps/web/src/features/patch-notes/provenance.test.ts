import { describe, expect, it } from "vitest";

import { provenanceRows } from "./provenance";

describe("provenanceRows", () => {
  it("keeps historical entries without metadata unchanged", () => {
    expect(provenanceRows()).toEqual([]);
    expect(provenanceRows(null)).toEqual([]);
  });

  it("renders only populated optional metadata in stable order", () => {
    expect(provenanceRows({
      development_era: "Human + Codex-centered workflow",
      reviewer: null,
      final_approval: "Human",
      verification: "2701 passed, 1 skipped",
      source_baseline: "6aa4e398",
      provenance_baseline: "c94746b",
    })).toEqual([
      { label: "Development Era", value: "Human + Codex-centered workflow", mono: undefined },
      { label: "Final Approval", value: "Human", mono: undefined },
      { label: "Verification", value: "2701 passed, 1 skipped", mono: undefined },
      { label: "Source Baseline", value: "6aa4e398", mono: true },
      { label: "Provenance Baseline", value: "c94746b", mono: true },
    ]);
  });
});
