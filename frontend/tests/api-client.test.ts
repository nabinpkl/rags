import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchCatalogPapers, fetchCoverage } from "@/lib/api-client";

function stubFetch() {
  const fetchMock = vi.fn(async (_url: string) => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("getJson's data version", () => {
  it("stamps every GET with the deploy's version, so the edge cache keys on it", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_VERSION", "3f9a1c0b7d2e");
    const fetchMock = stubFetch();

    await fetchCoverage();
    await fetchCatalogPapers({ sort: "cited", offset: 48 });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/coverage?v=3f9a1c0b7d2e");
    const url = new URL(fetchMock.mock.calls[1][0], "https://example.test");
    expect(url.searchParams.get("v")).toBe("3f9a1c0b7d2e");
    expect(url.searchParams.get("sort")).toBe("cited");
    expect(url.searchParams.get("offset")).toBe("48");
  });

  it("adds nothing when the build has no version (dev, tests)", async () => {
    vi.stubEnv("NEXT_PUBLIC_DATA_VERSION", "");
    const fetchMock = stubFetch();

    await fetchCoverage();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/coverage");
  });
});
