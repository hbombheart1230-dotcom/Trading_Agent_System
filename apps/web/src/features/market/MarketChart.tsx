import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatNumber, formatPct } from "../../shared/formatters/numbers";
import type { MarketSeries } from "./types";

export function MarketChart({ series }: { series: MarketSeries }) {
  const data = series.points.map((point) => ({ ...point, label: point.day.slice(5) }));
  const useChange = data.some((point) => point.change_pct != null);
  const key = useChange ? "change_pct" : "value";
  return <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 8, right: 10, left: 0, bottom: 0 }}><CartesianGrid stroke="#e6ebe8" strokeDasharray="2 3" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 10, fill: "#7d8782" }} axisLine={false} tickLine={false} /><YAxis tick={{ fontSize: 10, fill: "#7d8782" }} axisLine={false} tickLine={false} width={52} /><ReferenceLine y={0} stroke="#aeb8b3" /><Tooltip content={({ active, payload, label }) => { if (!active || !payload?.[0]) return null; const row = payload[0].payload as MarketSeries["points"][number]; return <div className="chart-tooltip"><strong>{label}</strong><div>값 {formatNumber(row.value, 3)}</div><div>변동 {formatPct(row.change_pct, true)}</div></div>; }} /><Line type="monotone" dataKey={key} stroke="#087f78" strokeWidth={2} dot={{ r: 2 }} connectNulls /></LineChart></ResponsiveContainer></div>;
}
