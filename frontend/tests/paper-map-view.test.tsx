import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "dark" }) }));
vi.mock("next/dynamic", () => ({ default: () => () => <div data-testid="canvas" /> }));
vi.mock("@/lib/paper-map/paper-map-data", async (orig) => ({
  ...(await orig<typeof import("@/lib/paper-map/paper-map-data")>()),
  fetchMap: vi.fn(async () => ({
    meta: {
      version: 1,
      digest: "abc123",
      generated: "2026-10-15",
      from_month: "2607",
      to_month: "2610",
      n: 3,
      unthemed: 1,
      bounds: [0, 0, 1, 1],
      themes: [{ name: "robot · arm", size: 2, cx: 0, cy: 0, top_category: "cs.RO", group: 0 }],
      groups: [{ name: "robotics · world", size: 2, cx: 0, cy: 0 }],
    },
    points: { n: 3, x: new Float32Array(3), y: new Float32Array(3), theme: new Int16Array(3) },
  })),
  fetchPapers: vi.fn(async () => ({ ids: [], versions: [], titles: [] })),
}));

import { PaperMapView } from "@/components/paper-map/paper-map-view";

function wrap({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("PaperMapView", () => {
  it("shows the themes, the unthemed count, and starts brighter in dark mode", async () => {
    render(<PaperMapView scope="recent" />, { wrapper: wrap });
    expect(await screen.findByText("robotics · world")).toBeInTheDocument();
    expect(screen.getByTestId("canvas")).toBeInTheDocument();
    expect(screen.getByLabelText(/hide papers with no theme/i)).not.toBeChecked();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByRole("slider")).toHaveValue("40");
  });
});
