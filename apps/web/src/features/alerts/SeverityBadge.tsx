import { SEVERITY_LABELS } from "./labels";
import type { AnomalySeverity } from "./types";

export function SeverityBadge({ severity }: { severity: AnomalySeverity }) {
  return <span className={`severity-badge severity-${severity.toLowerCase()}`}>{SEVERITY_LABELS[severity]}</span>;
}
