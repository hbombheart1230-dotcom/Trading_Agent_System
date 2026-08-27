import { formatDateTime } from "../../shared/formatters/dates";
import { formatNumber, formatPct, toneFor } from "../../shared/formatters/numbers";
import { SortableHeaderRow, type SortableColumn } from "../../shared/tables/SortableHeaderRow";
import { timestamp, type SortValue } from "../../shared/tables/sorting";
import { useSortableRows } from "../../shared/tables/useSortableRows";
import type { OpportunityOutcome } from "./types";

type OutcomeSortKey = "symbol" | "time" | "score" | "gross" | "live" | "mock" | "mfe" | "mae";
const COLUMNS: Array<SortableColumn<OutcomeSortKey>> = [
  { key: "symbol", label: "종목" }, { key: "time", label: "관측 시각" }, { key: "score", label: "Score" },
  { key: "gross", label: "Gross" }, { key: "live", label: "Live-equivalent" },
  { key: "mock", label: "Mock net" }, { key: "mfe", label: "MFE" }, { key: "mae", label: "MAE" },
];

function checkpoint(outcome: OpportunityOutcome, horizon: string) {
  return outcome.checkpoints.find((item) => item.horizon === horizon);
}

export function OpportunityOutcomeTable({ outcomes, horizon }: { outcomes: OpportunityOutcome[]; horizon: string }) {
  const sorted = useSortableRows(outcomes, (outcome, key): SortValue => {
    const point = checkpoint(outcome, horizon);
    if (key === "symbol") return outcome.symbol_name ?? outcome.symbol;
    if (key === "time") return timestamp(outcome.observed_at);
    if (key === "score") return outcome.score;
    if (key === "gross") return point?.gross_return_pct;
    if (key === "live") return point?.live_equivalent_net_return_pct;
    if (key === "mock") return point?.mock_broker_net_return_pct;
    if (key === "mfe") return point?.maximum_favorable_excursion_pct;
    return point?.maximum_adverse_excursion_pct;
  });
  return <div className="data-table-wrap"><table className="data-table sortable-table">
    <thead><SortableHeaderRow columns={COLUMNS} sort={sorted.sort} onSort={sorted.toggleSort} /></thead>
    <tbody>{sorted.rows.map((outcome) => { const point = checkpoint(outcome, horizon); return <tr key={outcome.opportunity_id}><td className="symbol-cell"><strong>{outcome.symbol_name ?? outcome.symbol}</strong><span>{outcome.symbol} · Rank {outcome.rank ?? "-"}</span></td><td>{formatDateTime(outcome.observed_at)}</td><td>{formatNumber(outcome.score, 3)}</td><td className={toneFor(point?.gross_return_pct)}>{formatPct(point?.gross_return_pct, true)}</td><td className={toneFor(point?.live_equivalent_net_return_pct)}>{formatPct(point?.live_equivalent_net_return_pct, true)}</td><td className={toneFor(point?.mock_broker_net_return_pct)}>{formatPct(point?.mock_broker_net_return_pct, true)}</td><td className="positive">{formatPct(point?.maximum_favorable_excursion_pct, true)}</td><td className="negative">{formatPct(point?.maximum_adverse_excursion_pct)}</td></tr>; })}</tbody>
  </table></div>;
}
