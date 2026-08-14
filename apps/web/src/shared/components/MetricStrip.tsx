import type { ReactNode } from "react";

export interface MetricItem {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "positive" | "negative" | "neutral";
}

export function MetricStrip({ items }: { items: MetricItem[] }) {
  return (
    <section className="metric-strip">
      {items.map((item) => (
        <div className="metric-cell" key={item.label}>
          <div className="metric-label">{item.label}</div>
          <div className={`metric-value ${item.tone ?? "neutral"}`}>{item.value}</div>
          {item.note && <div className="metric-note">{item.note}</div>}
        </div>
      ))}
    </section>
  );
}
