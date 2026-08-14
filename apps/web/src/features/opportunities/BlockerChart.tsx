import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatPct } from "../../shared/formatters/numbers";
import type { OpportunityFunnel } from "./types";

export function BlockerChart({ blockers }: { blockers: OpportunityFunnel["blockers"] }) {
  const data = blockers.map((item) => ({ ...item, label: item.reason.replaceAll("_", " ") }));
  return <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ left: 16, right: 14 }}><CartesianGrid stroke="#e6ebe8" strokeDasharray="2 3" horizontal={false} /><XAxis type="number" tick={{ fontSize: 10, fill: "#7d8782" }} axisLine={false} tickLine={false} /><YAxis type="category" dataKey="label" width={150} tick={{ fontSize: 9, fill: "#59635f" }} axisLine={false} tickLine={false} /><Tooltip content={({ active, payload }) => { if (!active || !payload?.[0]) return null; const row = payload[0].payload as OpportunityFunnel["blockers"][number]; return <div className="chart-tooltip"><strong>{row.reason}</strong><div>후보 {row.candidate_count}건 / 관측 {row.observed_count}건</div><div>평균 {formatPct(row.average_latest_return_pct, true)}</div><div>놓친 기회 {formatPct(row.missed_opportunity_rate != null ? row.missed_opportunity_rate * 100 : null)}</div></div>; }} /><Bar dataKey="candidate_count" fill="#c17b12" radius={[0, 3, 3, 0]} maxBarSize={22} /></BarChart></ResponsiveContainer></div>;
}
