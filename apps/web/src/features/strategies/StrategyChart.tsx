import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatPct } from "../../shared/formatters/numbers";
import type { StrategyPerformance } from "./types";

export function StrategyChart({ items }: { items: StrategyPerformance["items"] }) {
  const data = items.filter((item) => item.resolved_count > 0).slice(0, 12);
  return <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 42 }}><CartesianGrid stroke="#e6ebe8" strokeDasharray="2 3" vertical={false} /><XAxis dataKey="label" interval={0} angle={-28} textAnchor="end" tick={{ fontSize: 9, fill: "#59635f" }} axisLine={false} tickLine={false} /><YAxis tick={{ fontSize: 10, fill: "#7d8782" }} axisLine={false} tickLine={false} /><Tooltip content={({ active, payload }) => { if (!active || !payload?.[0]) return null; const row = payload[0].payload as StrategyPerformance["items"][number]; return <div className="chart-tooltip"><strong>{row.label}</strong><div>평균 {formatPct(row.average_return_pct, true)}</div><div>승률 {formatPct(row.win_rate != null ? row.win_rate * 100 : null)}</div><div>표본 {row.resolved_count}/{row.trade_count}</div></div>; }} /><Bar dataKey="average_return_pct" maxBarSize={34}>{data.map((item) => <Cell key={item.key} fill={(item.average_return_pct ?? 0) >= 0 ? "#18794e" : "#ba3a3a"} />)}</Bar></BarChart></ResponsiveContainer></div>;
}
