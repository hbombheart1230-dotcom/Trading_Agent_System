import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { stageLabel } from "./labels";
import type { LlmStageUsage } from "./types";

export function LlmStageChart({ stages }: { stages: LlmStageUsage[] }) {
  const data = stages.map((stage) => ({ ...stage, display: stageLabel(stage.stage_label) }));
  return <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ top: 5, right: 18, left: 24, bottom: 5 }}><CartesianGrid stroke="#e6ebe8" strokeDasharray="2 3" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fontSize: 10, fill: "#7d8782" }} axisLine={false} tickLine={false} /><YAxis type="category" dataKey="display" width={138} tick={{ fontSize: 9, fill: "#59635f" }} axisLine={false} tickLine={false} /><Tooltip content={({ active, payload }) => { if (!active || !payload?.[0]) return null; const row = payload[0].payload as LlmStageUsage & { display: string }; return <div className="chart-tooltip"><strong>{row.display}</strong><div>호출 {row.call_count}회</div><div>성공 {row.success_count}회</div><div>실패 {row.failure_count}회</div></div>; }} /><Bar dataKey="call_count" fill="#087f78" maxBarSize={26} radius={[0, 2, 2, 0]} /></BarChart></ResponsiveContainer></div>;
}
