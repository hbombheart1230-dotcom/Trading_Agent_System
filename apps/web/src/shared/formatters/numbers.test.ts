import { describe, expect, it } from "vitest";

import { formatPct, formatRatioPct, toneFor } from "./numbers";

describe("financial display formatters", () => {
  it("keeps ratio and percent units distinct", () => {
    expect(formatPct(1.25, true)).toBe("+1.25%");
    expect(formatRatioPct(0.125)).toBe("12.5%");
  });

  it("does not invent a directional tone for missing values", () => {
    expect(toneFor(null)).toBe("neutral");
    expect(toneFor(-0.01)).toBe("negative");
    expect(toneFor(0.01)).toBe("positive");
  });
});
