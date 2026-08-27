import { useMemo, useState } from "react";

import { nextSort, sortRows, type SortState, type SortValue } from "./sorting";

export function useSortableRows<T, K extends string>(
  rows: T[],
  valueFor: (row: T, key: K) => SortValue,
) {
  const [sort, setSort] = useState<SortState<K> | null>(null);
  const sortedRows = useMemo(
    () => sort ? sortRows(rows, (row) => valueFor(row, sort.key), sort.direction) : rows,
    [rows, sort, valueFor],
  );
  const toggleSort = (key: K) => setSort((current) => nextSort(current, key));
  return { rows: sortedRows, sort, toggleSort };
}
