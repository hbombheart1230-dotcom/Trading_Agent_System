import { describe, expect, it } from "vitest";

import { ageLabel, marketStateLabel, runtimeStateLabel, runtimeStateTone } from "./presentation";
import type { RuntimeStatus } from "./types";

describe("runtime status presentation", () => {
  it("keeps normal close distinct from a failure", () => {
    expect(runtimeStateLabel("STOPPED_EXPECTED")).toBe("MAIN 정상 종료");
    expect(runtimeStateTone("STOPPED_EXPECTED")).toBe("runtime-stopped-expected");
    expect(runtimeStateTone("STOPPED_UNEXPECTED")).toBe("runtime-error");
  });

  it("formats heartbeat age without hiding long delays", () => {
    expect(ageLabel(30)).toBe("30초 전");
    expect(ageLabel(180)).toBe("3분 전");
    expect(ageLabel(7200)).toBe("2시간 전");
  });

  it("does not present a stale market label as the current session", () => {
    const runtime = {
      market: {
        label: "after_hours_single_price_open",
        expected_running: false,
        expectation_source: "OFF_HOURS_CLOCK",
      },
    } as RuntimeStatus;
    expect(marketStateLabel(runtime)).toBe("\uc7a5\uc678 / \uc2e4\ud589 \ube44\ub300\uc0c1");
  });
});
