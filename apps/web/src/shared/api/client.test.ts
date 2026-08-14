import { describe, expect, it } from "vitest";

import { query } from "./client";

describe("query", () => {
  it("omits empty values and encodes parameters", () => {
    expect(query("/api/v1/trades", { start: "2026-08-01", symbol: "005930", result: undefined })).toBe(
      "/api/v1/trades?start=2026-08-01&symbol=005930",
    );
  });
});
