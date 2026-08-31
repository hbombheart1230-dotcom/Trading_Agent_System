import type { Availability } from "../../shared/api/types";

export interface PatchNoteProvenance {
  development_era?: string | null;
  owner?: string | null;
  reviewer?: string | null;
  final_approval?: string | null;
  verification?: string | null;
  source_baseline?: string | null;
  provenance_baseline?: string | null;
}

export interface PatchNoteEntry {
  date: string;
  version: string;
  title: string;
  stage: string;
  types: string[];
  summary: string;
  details: string[];
  impact: string;
  sources: string[];
  status: string;
  provenance?: PatchNoteProvenance | null;
}

export interface PatchNotesResponse {
  status: Availability;
  schema_version: string;
  generated_for: string;
  entry_count: number;
  stages: string[];
  types: string[];
  entries: PatchNoteEntry[];
  reason: string | null;
  read_only: boolean;
  execution_callable: boolean;
}
