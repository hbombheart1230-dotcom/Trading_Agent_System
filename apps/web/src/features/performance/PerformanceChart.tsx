import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatKrw, formatPct } from "../../shared/formatters/numbers";
import type { PerformancePoint } from "./types";

export function PerformanceChart({ points }: { points: PerformancePoint[] }) {
  const data = points.map((point) => ({
    ...point,
    label: point.day.slice(5),
  }));
  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 10, left: 6, bottom: 0 }}>
          <defs>
            <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#087f78" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#087f78" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e6ebe8" strokeDasharray="2 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#7d8782" }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="pnl" tick={{ fontSize: 10, fill: "#7d8782" }} axisLine={false} tickLine={false} width={54} />
          <YAxis yAxisId="return" orientation="right" tick={{ fontSize: 10, fill: "#7d8782" }} axisLine={false} tickLine={false} width={42} />
          <Tooltip content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const row = payload[0].payload as PerformancePoint;
            return <div className="chart-tooltip"><strong>{label}</strong><div>누적 손익 {formatKrw(row.cumulative_realized_pnl_krw)}</div><div>평균 수익률 {formatPct(row.average_trade_return_pct, true)}</div><div>표본 {row.sample_count}건</div></div>;
          }} />
          <Area yAxisId="pnl" type="monotone" dataKey="cumulative_realized_pnl_krw" stroke="#087f78" strokeWidth={2} fill="url(#pnlFill)" connectNulls />
          <Line yAxisId="return" type="monotone" dataKey="average_trade_return_pct" stroke="#c17b12" strokeWidth={1.5} dot={{ r: 2 }} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
