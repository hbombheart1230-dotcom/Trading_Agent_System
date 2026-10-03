import { describe, expect, it } from "vitest";

import { nextSort, sortRows, timestamp } from "./sorting";

describe("shared table sorting", () => {
  it("sorts stably and leaves the source unchanged", () => {
    const rows = [{ id: "a", value: 2 }, { id: "b", value: 1 }, { id: "c", value: 2 }];
    expect(sortRows(rows, (row) => row.value, "asc").map((row) => row.id)).toEqual(["b", "a", "c"]);
    expect(rows.map((row) => row.id)).toEqual(["a", "b", "c"]);
  });

  it("keeps missing and invalid numbers last", () => {
    const rows = [{ value: null }, { value: 3 }, { value: Number.NaN }, { value: 1 }];
    expect(sortRows(rows, (row) => row.value, "desc").map((row) => row.value)).toEqual([3, 1, null, Number.NaN]);
  });

  it("toggles only the active key and parses timestamps", () => {
    expect(nextSort(null, "score")).toEqual({ key: "score", direction: "asc" });
    expect(nextSort({ key: "score", direction: "asc" }, "score")).toEqual({ key: "score", direction: "desc" });
    expect(nextSort({ key: "score", direction: "desc" }, "name")).toEqual({ key: "name", direction: "asc" });
    expect(timestamp("2026-08-27T00:00:00Z")).toBeGreaterThan(0);
    expect(timestamp("invalid")).toBeNull();
  });
});
