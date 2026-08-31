import type { PatchNoteProvenance } from "./types";

export interface ProvenanceRow {
  label: string;
  value: string;
  mono?: boolean;
}

const DEFINITIONS: Array<[keyof PatchNoteProvenance, string, boolean?]> = [
  ["development_era", "Development Era"],
  ["owner", "Owner"],
  ["reviewer", "Reviewer"],
  ["final_approval", "Final Approval"],
  ["verification", "Verification"],
  ["source_baseline", "Source Baseline", true],
  ["provenance_baseline", "Provenance Baseline", true],
];

export function provenanceRows(provenance?: PatchNoteProvenance | null): ProvenanceRow[] {
  if (!provenance) return [];
  return DEFINITIONS.flatMap(([key, label, mono]) => {
    const value = provenance[key]?.trim();
    return value ? [{ label, value, mono }] : [];
  });
}
