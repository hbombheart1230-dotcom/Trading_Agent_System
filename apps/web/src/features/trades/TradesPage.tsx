import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { query } from "../../shared/api/client";
import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { DateRange } from "../../shared/components/DateRange";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { isoDayOffset } from "../../shared/formatters/dates";
import { TradeDetailPanel } from "./TradeDetailPanel";
import { TradeTable } from "./TradeTable";
import type { TradeDetail, TradeList } from "./types";

export function TradesPage() {
  const [start, setStart] = useState(isoDayOffset(-90));
  const [end, setEnd] = useState(isoDayOffset(0));
  const [symbol, setSymbol] = useState("");
  const [result, setResult] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const listPath = useMemo(() => query("/api/v1/trades", { start, end, symbol: symbol.trim() || undefined, result: result || undefined, limit: 100 }), [start, end, symbol, result]);
  const trades = useApi<TradeList>(listPath);
  const detail = useApi<TradeDetail>(selectedId ? `/api/v1/trades/${encodeURIComponent(selectedId)}` : null);

  return (
    <>
      <PageHeader title="거래" description="거래 결과에서 Scanner 선택, Monitor 진입·청산, horizon과 artifact 정합성까지 추적합니다." actions={<DateRange start={start} end={end} onChange={(a, b) => { setStart(a); setEnd(b); setSelectedId(null); }} />} />
      <Panel title="거래 내역" meta={`${trades.data?.total_count ?? 0}건`}>
        <div className="toolbar" style={{ marginBottom: 13 }}>
          <Search size={16} className="muted" />
          <input className="filter-input" value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="종목코드 검색" aria-label="종목코드" />
          <select className="filter-select" value={result} onChange={(event) => setResult(event.target.value)} aria-label="결과 필터"><option value="">전체 결과</option><option value="win">수익</option><option value="loss">손실</option><option value="flat">보합</option></select>
          {trades.data && <span className="muted">Artifact 이슈 {trades.data.issue_count}건</span>}
        </div>
        <DataState loading={trades.loading} error={trades.error} empty={!trades.data?.items.length} onRetry={trades.refresh}><TradeTable items={trades.data?.items ?? []} selectedId={selectedId} onSelect={setSelectedId} /></DataState>
      </Panel>
      {selectedId && <div className="page-grid" style={{ marginTop: 14 }}><TradeDetailPanel state={detail} /></div>}
    </>
  );
}
