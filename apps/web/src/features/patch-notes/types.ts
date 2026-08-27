import type { Availability } from "../../shared/api/types";

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
