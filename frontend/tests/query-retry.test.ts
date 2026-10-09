import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api-client";
import { retryUnlessMissing } from "@/lib/query-retry";

describe("retryUnlessMissing", () => {
  it("never retries a 404 — the record is missing, not the request", () => {
    expect(retryUnlessMissing(0, new ApiError("/api/papers/9999.99999", 404))).toBe(false);
  });

  it("retries a server error the default three times, then stops", () => {
    const boom = new ApiError("/api/papers/1409.7842", 503);
    expect(retryUnlessMissing(0, boom)).toBe(true);
    expect(retryUnlessMissing(2, boom)).toBe(true);
    expect(retryUnlessMissing(3, boom)).toBe(false);
  });

  it("retries a transport failure, which carries no status at all", () => {
    expect(retryUnlessMissing(0, new TypeError("Failed to fetch"))).toBe(true);
  });
});
