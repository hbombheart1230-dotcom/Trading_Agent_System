import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import type { SortState } from "./sorting";

export interface SortableColumn<K extends string> {
  key: K;
  label: string;
}

interface Props<K extends string> {
  columns: Array<SortableColumn<K>>;
  sort: SortState<K> | null;
  onSort: (key: K) => void;
}

export function SortableHeaderRow<K extends string>({ columns, sort, onSort }: Props<K>) {
  return (
    <tr>
      {columns.map((column) => {
        const active = sort?.key === column.key;
        const direction = active ? sort.direction : null;
        const Icon = direction === "asc" ? ArrowUp : direction === "desc" ? ArrowDown : ArrowUpDown;
        return (
          <th key={column.key} aria-sort={direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none"}>
            <button
              type="button"
              className={`sortable-header${active ? " active" : ""}`}
              onClick={() => onSort(column.key)}
              title={`${column.label} ${direction === "asc" ? "내림차순" : "오름차순"} 정렬`}
            >
              <span>{column.label}</span><Icon size={13} />
            </button>
          </th>
        );
      })}
    </tr>
  );
}
