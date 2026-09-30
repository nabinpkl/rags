// The panel that is a column on a desktop and a drawer on a phone. Three
// things must hold, and all three are easy to break by "simplifying" it:
//   1. its child mounts ONCE (the agent panel owns the SSE subscription),
//   2. a closed drawer is out of the tab order, not just off-screen,
//   3. it only claims dialog semantics while it actually is a dialog.
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DrawerPanel } from "@/components/shell/drawer-panel";
import { MEDIA_AGENT_DOCKED, MEDIA_FILTERS_DOCKED } from "@/lib/breakpoints";

function installMatchMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    media: query,
    matches,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("DrawerPanel — docked", () => {
  it("is a plain region, not a dialog", () => {
    installMatchMedia(true);
    render(
      <DrawerPanel dockAt="lg" side="right" label="Agent panel" open={false} onClose={() => {}}>
        <p>panel body</p>
      </DrawerPanel>,
    );
    expect(screen.getByRole("region", { name: "Agent panel" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows its content even though `open` is false — docking ignores it", () => {
    installMatchMedia(true);
    render(
      <DrawerPanel dockAt="lg" side="right" label="Agent panel" open={false} onClose={() => {}}>
        <p>panel body</p>
      </DrawerPanel>,
    );
    expect(screen.getByText("panel body")).toBeInTheDocument();
    // No backdrop over the app when the panel is simply a column.
    expect(screen.queryByRole("button", { name: /close agent panel/i })).not.toBeInTheDocument();
  });
});

describe("DrawerPanel — docked, put away", () => {
  it("hides the column when dockedOpen is false, and keeps the child mounted", () => {
    installMatchMedia(true);
    const { rerender } = render(
      <DrawerPanel
        dockAt="lg"
        side="right"
        label="Agent panel"
        open={false}
        dockedOpen={false}
        onClose={() => {}}
      >
        <p>panel body</p>
      </DrawerPanel>,
    );
    const region = screen.getByRole("region", { name: "Agent panel", hidden: true });
    expect(region).toHaveClass("lg:hidden");
    // Still in the DOM: the agent panel owns the SSE stream, and a column
    // put away mid-turn must not drop it.
    expect(screen.getByText("panel body")).toBeInTheDocument();

    rerender(
      <DrawerPanel
        dockAt="lg"
        side="right"
        label="Agent panel"
        open={false}
        dockedOpen
        onClose={() => {}}
      >
        <p>panel body</p>
      </DrawerPanel>,
    );
    expect(screen.getByRole("region", { name: "Agent panel" })).not.toHaveClass("lg:hidden");
  });
});

describe("DrawerPanel — drawer", () => {
  it("keeps a closed drawer out of the accessibility tree and tab order", () => {
    installMatchMedia(false);
    render(
      <DrawerPanel dockAt="lg" side="right" label="Agent panel" open={false} onClose={() => {}}>
        <button type="button">composer</button>
      </DrawerPanel>,
    );
    // `invisible` (visibility: hidden) rather than a transform alone: a
    // translated-off-screen panel still takes tab stops.
    expect(screen.getByRole("dialog", { name: "Agent panel", hidden: true })).toHaveClass(
      "invisible",
    );
  });

  it("carries dialog semantics and a backdrop when open", () => {
    installMatchMedia(false);
    render(
      <DrawerPanel dockAt="lg" side="right" label="Agent panel" open onClose={() => {}}>
        <p>panel body</p>
      </DrawerPanel>,
    );
    const dialog = screen.getByRole("dialog", { name: "Agent panel" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveClass("visible");
    expect(screen.getByRole("button", { name: /close agent panel/i })).toBeInTheDocument();
  });

  it("closes on Escape", () => {
    installMatchMedia(false);
    const onClose = vi.fn();
    render(
      <DrawerPanel dockAt="md" side="left" label="Facet filters" open onClose={onClose}>
        <p>filters</p>
      </DrawerPanel>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when the backdrop is tapped", () => {
    installMatchMedia(false);
    const onClose = vi.fn();
    render(
      <DrawerPanel dockAt="md" side="left" label="Facet filters" open onClose={onClose}>
        <p>filters</p>
      </DrawerPanel>,
    );
    fireEvent.click(screen.getByRole("button", { name: /close facet filters/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not fire Escape handlers while closed", () => {
    installMatchMedia(false);
    const onClose = vi.fn();
    render(
      <DrawerPanel dockAt="md" side="left" label="Facet filters" open={false} onClose={onClose}>
        <p>filters</p>
      </DrawerPanel>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("moves focus into the panel on open", () => {
    installMatchMedia(false);
    render(
      <DrawerPanel dockAt="lg" side="right" label="Agent panel" open onClose={() => {}}>
        <p>panel body</p>
      </DrawerPanel>,
    );
    expect(screen.getByRole("dialog", { name: "Agent panel" })).toHaveFocus();
  });
});

describe("DrawerPanel — the single-instance invariant", () => {
  it("renders its child exactly once in either mode", () => {
    for (const docked of [true, false]) {
      installMatchMedia(docked);
      const { unmount } = render(
        <DrawerPanel dockAt="lg" side="right" label="Agent panel" open onClose={() => {}}>
          <p data-testid="child">panel body</p>
        </DrawerPanel>,
      );
      // Two copies would mean two SSE subscriptions and duplicate DOM ids.
      expect(screen.getAllByTestId("child")).toHaveLength(1);
      unmount();
      vi.unstubAllGlobals();
    }
  });

  it("asks about the same breakpoints its Tailwind classes switch on", () => {
    // The CSS thresholds (`md:`/`lg:`) and these queries are two spellings of
    // one number; if they drift, a panel is styled as a column while being
    // announced as a dialog.
    expect(MEDIA_FILTERS_DOCKED).toBe("(min-width: 768px)");
    expect(MEDIA_AGENT_DOCKED).toBe("(min-width: 1024px)");

    const queried: string[] = [];
    vi.stubGlobal("matchMedia", (query: string) => {
      queried.push(query);
      return { media: query, matches: true, addEventListener() {}, removeEventListener() {} };
    });
    render(
      <DrawerPanel dockAt="md" side="left" label="Facet filters" open={false} onClose={() => {}}>
        <p>filters</p>
      </DrawerPanel>,
    );
    expect(queried).toContain(MEDIA_FILTERS_DOCKED);
  });
});
