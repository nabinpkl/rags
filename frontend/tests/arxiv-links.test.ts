import { describe, expect, it } from "vitest";

import { arxivAbsUrl, arxivPdfUrl } from "@/lib/arxiv-links";

describe("arxiv links — §6b/D9 version pinning", () => {
  it("pins the PDF URL to the exact version when one is known", () => {
    expect(arxivPdfUrl("2401.00001", "v3")).toBe("https://arxiv.org/pdf/2401.00001v3");
  });

  it("pins the abs URL too — a bare /abs follows the paper as it is revised", () => {
    expect(arxivAbsUrl("2401.00001", "v3")).toBe("https://arxiv.org/abs/2401.00001v3");
  });

  it("falls back to the unpinned URL when version is NULL (pre-backfill stragglers, D9)", () => {
    expect(arxivPdfUrl("2401.00001", null)).toBe("https://arxiv.org/pdf/2401.00001");
    expect(arxivAbsUrl("2401.00001", null)).toBe("https://arxiv.org/abs/2401.00001");
    expect(arxivAbsUrl("2401.00001")).toBe("https://arxiv.org/abs/2401.00001");
  });

  it("never points anywhere but arxiv.org — never our own origin (§6b)", () => {
    for (const url of [arxivPdfUrl("2401.00001", "v1"), arxivAbsUrl("2401.00001", "v1")]) {
      expect(new URL(url).origin).toBe("https://arxiv.org");
    }
  });
});
