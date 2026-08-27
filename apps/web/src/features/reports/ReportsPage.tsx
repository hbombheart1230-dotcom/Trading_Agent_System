import { FileJson, FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { query } from "../../shared/api/client";
import { useApi } from "../../shared/api/useApi";
import { DataState } from "../../shared/components/DataState";
import { PageHeader } from "../../shared/components/PageHeader";
import { Panel } from "../../shared/components/Panel";
import { isoDayOffset } from "../../shared/formatters/dates";
import type { ReportCatalog, ReportContent, TradeList } from "../trades/types";

export function ReportsPage() {
  const trades = useApi<TradeList>(query("/api/v1/trades", { start: isoDayOffset(-45), end: isoDayOffset(0), limit: 100 }));
  const [tradeId, setTradeId] = useState<string | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);

  useEffect(() => {
    if (!tradeId && trades.data?.items[0]) setTradeId(trades.data.items[0].trade_id);
  }, [tradeId, trades.data]);

  const catalog = useApi<ReportCatalog>(tradeId ? `/api/v1/trades/${encodeURIComponent(tradeId)}/reports` : null);

  useEffect(() => {
    setReportId(catalog.data?.reports.find((report) => report.available)?.report_id ?? null);
  }, [catalog.data]);

  const content = useApi<ReportContent>(
    tradeId && reportId
      ? `/api/v1/trades/${encodeURIComponent(tradeId)}/reports/${encodeURIComponent(reportId)}`
      : null,
  );

  return (
    <>
      <PageHeader
        title="리포트"
        description="저장된 거래 분석 리포트를 안전한 plain text 또는 정제 JSON으로 조회합니다."
      />
      <div className="split-view">
        <Panel title="거래 선택" meta={`${trades.data?.total_count ?? 0}건`}>
          <DataState loading={trades.loading} error={trades.error} empty={!trades.data?.items.length} onRetry={trades.refresh}>
            <div className="data-table-wrap">
              <table className="data-table">
                <tbody>
                  {trades.data?.items.map((trade) => (
                    <tr
                      key={trade.trade_id}
                      className="clickable"
                      onClick={() => { setTradeId(trade.trade_id); setReportId(null); }}
                      style={trade.trade_id === tradeId ? { background: "#edf8f5" } : undefined}
                    >
                      <td className="symbol-cell">
                        <strong>{trade.symbol_name ?? trade.symbol}</strong>
                        <span>{trade.day} · {trade.symbol}</span>
                      </td>
                      <td>{trade.result ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </DataState>
        </Panel>
        <Panel
          title={content.data?.title ?? "리포트 내용"}
          meta={catalog.data && `${catalog.data.reports.filter((report) => report.available).length}개 사용 가능`}
        >
          {catalog.data && (
            <div className="toolbar" style={{ marginBottom: 12 }}>
              {catalog.data.reports.filter((report) => report.available).map((report) => (
                <button
                  key={report.report_id}
                  className={`icon-button ${reportId === report.report_id ? "active" : ""}`}
                  style={{ width: "auto", padding: "0 9px", gap: 6, display: "inline-flex" }}
                  onClick={() => setReportId(report.report_id)}
                  title={report.title}
                >
                  {report.format === "json" ? <FileJson size={15} /> : <FileText size={15} />}
                  {report.title}
                </button>
              ))}
            </div>
          )}
          <DataState
            loading={catalog.loading || content.loading}
            error={catalog.error || content.error}
            empty={!content.data}
            onRetry={() => { catalog.refresh(); content.refresh(); }}
          >
            {content.data?.markdown != null ? (
              <pre className="report-viewer">{content.data.markdown}</pre>
            ) : (
              <pre className="report-viewer">{JSON.stringify(content.data?.json_content, null, 2)}</pre>
            )}
          </DataState>
        </Panel>
      </div>
    </>
  );
}
