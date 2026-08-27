export type SortDirection = "asc" | "desc";
export type SortValue = number | string | boolean | null | undefined;

export interface SortState<K extends string> {
  key: K;
  direction: SortDirection;
}

const collator = new Intl.Collator("ko-KR", { numeric: true, sensitivity: "base" });

export function sortRows<T>(
  rows: T[],
  valueOf: (row: T) => SortValue,
  direction: SortDirection,
): T[] {
  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const leftValue = normalize(valueOf(left.row));
      const rightValue = normalize(valueOf(right.row));
      if (leftValue == null && rightValue == null) return left.index - right.index;
      if (leftValue == null) return 1;
      if (rightValue == null) return -1;

      const comparison = typeof leftValue === "number" && typeof rightValue === "number"
        ? leftValue - rightValue
        : collator.compare(String(leftValue), String(rightValue));
      return comparison === 0
        ? left.index - right.index
        : comparison * (direction === "asc" ? 1 : -1);
    })
    .map(({ row }) => row);
}

export function nextSort<K extends string>(current: SortState<K> | null, key: K): SortState<K> {
  return {
    key,
    direction: current?.key === key && current.direction === "asc" ? "desc" : "asc",
  };
}

export function timestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function normalize(value: SortValue): number | string | boolean | null {
  if (typeof value === "number" && !Number.isFinite(value)) return null;
  if (value === "") return null;
  return value ?? null;
}
