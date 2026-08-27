import { Activity, Clock3, GitBranch, Radio, ShieldCheck } from "lucide-react";

import { DataState } from "../../shared/components/DataState";
import { Panel } from "../../shared/components/Panel";
import { formatDateTime } from "../../shared/formatters/dates";
import { ageLabel, logicalSessionLabel, marketStateLabel, processTreeLabel } from "./presentation";
import { RuntimeStateBadge } from "./RuntimeStateBadge";
import { useRuntimeStatus } from "./RuntimeStatusContext";

export function RuntimeStatusPanel() {
  const runtime = useRuntimeStatus();
  const data = runtime.data;

  return (
    <Panel
      title="Trading Main"
      meta={data ? `15\ucd08 \uc790\ub3d9 \uac31\uc2e0 | ${formatDateTime(data.checked_at)}` : "\uc0c1\ud0dc \ud655\uc778 \uc911"}
      className="span-12"
    >
      <DataState loading={runtime.loading} error={runtime.error} empty={!data} onRetry={runtime.refresh}>
        {data && (
          <div className="runtime-status-grid">
            <div className="runtime-state-summary">
              <Activity size={18} />
              <div><span>{"\ub17c\ub9ac \ub7f0\ud0c0\uc784 \uc0c1\ud0dc"}</span><RuntimeStateBadge state={data.runtime_state} /></div>
            </div>
            <div className="runtime-status-item"><Clock3 size={15} /><span>Heartbeat</span><strong>{ageLabel(data.lock.heartbeat_age_seconds)}</strong></div>
            <div className="runtime-status-item"><GitBranch size={15} /><span>{"\ub17c\ub9ac \uc138\uc158"}</span><strong>{logicalSessionLabel(data)}</strong><small>{processTreeLabel(data)}</small></div>
            <div className="runtime-status-item"><ShieldCheck size={15} /><span>Watchdog</span><strong>{data.watchdog.ok === false ? "\uc810\uac80 \ud544\uc694" : ageLabel(data.watchdog.observation_age_seconds)}</strong><small>{data.watchdog.fresh ? "5\ubd84 \uc8fc\uae30 \uc815\uc0c1 \uad00\uce21" : "\ub9c8\uc9c0\ub9c9 \uc7a5\uc911 \uad00\uce21"}</small></div>
            <div className="runtime-status-item"><Radio size={15} /><span>{"\uc2dc\uc7a5 \uc0c1\ud0dc"}</span><strong>{marketStateLabel(data)}</strong><small>{data.market.expectation_source}</small></div>
          </div>
        )}
      </DataState>
    </Panel>
  );
}
