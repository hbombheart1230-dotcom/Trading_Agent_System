import { Bot, CheckCircle2, LogIn, LogOut, MoonStar, SunMedium } from "lucide-react";

import { formatDateTime } from "../../shared/formatters/dates";
import type { OperationsTimelineItem } from "./types";

const PHASE_ICON = {
  preopen: SunMedium,
  entry: LogIn,
  exit: LogOut,
  closeout: MoonStar,
} as const;

export function OperationsTimeline({ items, onSelectTrade }: { items: OperationsTimelineItem[]; onSelectTrade: (tradeId: string) => void }) {
  if (!items.length) return <div className="empty-line">표시할 운영 이벤트가 없습니다.</div>;
  return <div className="operations-timeline">
    {items.map((item) => {
      const Icon = PHASE_ICON[item.phase as keyof typeof PHASE_ICON] ?? Bot;
      return <button className="operations-timeline-item" type="button" key={item.event_id} disabled={!item.trade_id} onClick={() => item.trade_id && onSelectTrade(item.trade_id)}>
        <span className="operations-timeline-marker"><Icon size={15} /></span>
        <span className="operations-timeline-time">{item.expected_time_kst ? `${item.expected_time_kst} 예정` : formatDateTime(item.actual_time)}</span>
        <span className="operations-timeline-main"><strong>{item.title}</strong><small>{item.detail ?? item.source}</small></span>
        <span className={`operations-event-state ${item.status === "SUCCESS" || item.status === "FILLED" ? "event-ok" : "event-neutral"}`}><CheckCircle2 size={11} />{item.status}</span>
      </button>;
    })}
  </div>;
}
