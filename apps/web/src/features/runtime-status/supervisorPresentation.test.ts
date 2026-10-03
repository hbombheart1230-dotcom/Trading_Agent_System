import { describe, expect, it } from "vitest";

import { runtimeHistoryLabel, supervisorActionLabel, supervisorReasonLabel } from "./presentation";

describe("watchdog supervisor presentation", () => {
  it("explains recovery actions and machine reasons", () => {
    expect(supervisorActionLabel("RECOVERED")).toBe("복구 완료");
    expect(supervisorReasonLabel("heartbeat_stale")).toBe("Heartbeat 응답 지연");
  });

  it("keeps unknown diagnostics visible", () => {
    expect(supervisorReasonLabel("custom_reason")).toBe("custom_reason");
    expect(runtimeHistoryLabel("STALE")).toBe("응답 없음");
  });
});
