import { runtimeStateLabel, runtimeStateTone } from "./presentation";
import type { RuntimeState } from "./types";

export function RuntimeStateBadge({ state }: { state: RuntimeState }) {
  return <span className={`runtime-state-pill ${runtimeStateTone(state)}`}>{runtimeStateLabel(state)}</span>;
}
