import { useState } from "react";

import { query } from "../../shared/api/client";
import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { MetricStrip } from "../../shared/components/MetricStrip";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { StatusPill } from "../../shared/components/StatusPill";
import { formatDateTime, isoDayOffset } from "../../shared/formatters/dates";
import { formatNumber, formatPct, toneFor } from "../../shared/formatters/numbers";
import { MarketChart } from "./MarketChart";
import type { MarketSeries, MarketSnapshot } from "./types";

const SERIES_KEYS = ["kospi", "kosdaq", "kospi200", "krx_night_futures", "nasdaq", "sp500", "usdkrw", "dxy", "us_10y_yield"];

export function MarketPage() {
  const [metric, setMetric] = useState("kospi");
  const snapshot = useApi<MarketSnapshot>("/api/v1/market/snapshot");
  const series = useApi<MarketSeries>(query("/api/v1/market/series", { start: isoDayOffset(-20), end: isoDayOffset(0), metric }));
  const metrics = snapshot.data?.metrics ?? [];
  const find = (key: string) => metrics.find((item) => item.key === key);
  const breadth = snapshot.data?.breadth;
  return <>
    <PageHeader title="시장" description="국내외 지수, 금리, 환율, 야간선물과 시장 breadth를 매매 맥락으로 함께 봅니다." actions={snapshot.data && <><StatusPill status={snapshot.data.status} /><span className="muted">{formatDateTime(snapshot.data.source_generated_at)}</span></>} />
    <DataState loading={snapshot.loading} error={snapshot.error} onRetry={snapshot.refresh}>
      <MetricStrip items={[
        { label: "KOSPI", value: formatPct(find("kospi")?.change_pct, true), tone: toneFor(find("kospi")?.change_pct), note: formatNumber(find("kospi")?.value, 2) },
        { label: "KOSDAQ", value: formatPct(find("kosdaq")?.change_pct, true), tone: toneFor(find("kosdaq")?.change_pct), note: formatNumber(find("kosdaq")?.value, 2) },
        { label: "KRX 야간선물", value: formatPct(find("krx_night_futures")?.change_pct, true), tone: toneFor(find("krx_night_futures")?.change_pct), note: formatNumber(find("krx_night_futures")?.value, 2) },
        { label: "NASDAQ", value: formatPct(find("nasdaq")?.change_pct, true), tone: toneFor(find("nasdaq")?.change_pct), note: formatNumber(find("nasdaq")?.value, 2) },
        { label: "시장 Breadth", value: formatNumber(breadth?.breadth_ratio, 3), tone: toneFor(breadth?.breadth_ratio), note: `상승 ${breadth?.rising ?? 0} / 하락 ${breadth?.falling ?? 0}` },
      ]} />
    </DataState>
    <div className="page-grid" style={{ marginTop: 14 }}>
      <Panel title="시장 지표 추이" meta={`${series.data?.points.length ?? 0}일 관측`} className="span-8">
        <div className="toolbar" style={{ marginBottom: 12 }}><select className="filter-select" value={metric} onChange={(event) => setMetric(event.target.value)}>{SERIES_KEYS.map((key) => <option key={key} value={key}>{find(key)?.label ?? key}</option>)}</select>{series.data && <StatusPill status={series.data.status} />}</div>
        <DataState loading={series.loading} error={series.error} empty={!series.data?.points.length} onRetry={series.refresh}>{series.data && <MarketChart series={series.data} />}</DataState>
      </Panel>
      <Panel title="시장 압력" meta="source 그대로 표시" className="span-4">
        <div className="detail-stack">
          <div className="detail-row"><span>글로벌 감성</span><strong>{formatNumber(snapshot.data?.sentiment_score, 3)}</strong></div>
          <div className="detail-row"><span>USD/KRW</span><strong className={toneFor(find("usdkrw")?.change_pct)}>{formatPct(find("usdkrw")?.change_pct, true)}</strong></div>
          <div className="detail-row"><span>DXY</span><strong className={toneFor(find("dxy")?.change_pct)}>{formatPct(find("dxy")?.change_pct, true)}</strong></div>
          <div className="detail-row"><span>미국 10년물</span><strong>{formatNumber(find("us_10y_yield")?.value, 3)}%</strong></div>
          <div className="detail-row"><span>상승 / 하락 / 보합</span><strong>{breadth?.rising ?? 0} / {breadth?.falling ?? 0} / {breadth?.unchanged ?? 0}</strong></div>
          <div className="detail-row"><span>Sanity warning</span><strong>{snapshot.data?.warning_count ?? 0}건</strong></div>
        </div>
      </Panel>
      <Panel title="전체 수집 지표" meta={`${metrics.length}개`} className="span-12">
        <div className="data-table-wrap"><table className="data-table"><thead><tr><th>지표</th><th>구분</th><th>현재값</th><th>변동</th><th>역할</th><th>Source</th></tr></thead><tbody>{metrics.map((item) => <tr key={item.key}><td><strong>{item.label}</strong><div className="muted mono">{item.key}</div></td><td>{item.category}</td><td>{formatNumber(item.value, 4)} <span className="muted">{item.unit}</span></td><td className={toneFor(item.change_pct)}>{item.change_pct != null ? formatPct(item.change_pct, true) : formatNumber(item.change, 4)}</td><td>{item.role?.replaceAll("_", " ") ?? "-"}</td><td>{item.source ?? "-"}</td></tr>)}</tbody></table></div>
      </Panel>
    </div>
  </>;
}
