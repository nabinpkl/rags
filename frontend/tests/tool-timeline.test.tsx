import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolTimeline } from "@/components/agent-panel/tool-timeline";
import type { TimelineEntry } from "@/stores/agent-session-store";

describe("ToolTimeline", () => {
  it("renders tool_call and ui_action entries in order, resolved to ok/error only", () => {
    const entries: TimelineEntry[] = [
      {
        id: 1,
        call: { type: "tool_call", name: "search_corpus", args: { query: "chain of thought" } },
        result: { type: "tool_result_summary", name: "search_corpus", ok: true, error: null },
      },
      {
        id: 2,
        call: {
          type: "ui_action",
          action: "open_paper",
          args: { action: "open_paper", paper_id: "2401.00001" },
        },
        result: null,
      },
    ];
    render(<ToolTimeline entries={entries} />);

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("search_corpus");
    expect(rows[0]).toHaveTextContent("done");
    // §6c: never a chunk count, score, row, or payload — only name/args/ok.
    expect(rows[0]).not.toHaveTextContent(/chunk|score/i);
    expect(rows[1]).toHaveTextContent("open_paper");
    expect(rows[1]).toHaveTextContent("running"); // no paired result yet
  });

  it("renders a failed result's error text", () => {
    const entries: TimelineEntry[] = [
      {
        id: 1,
        call: { type: "tool_call", name: "read_paper", args: { paper_id: "9999.99999" } },
        result: {
          type: "tool_result_summary",
          name: "read_paper",
          ok: false,
          error: "no such paper",
        },
      },
    ];
    render(<ToolTimeline entries={entries} />);
    expect(screen.getByRole("listitem")).toHaveTextContent("no such paper");
    expect(screen.getByRole("listitem")).toHaveTextContent("failed");
  });

  it("does not crash on an unrecognized future call shape (forward-compat)", () => {
    const entries = [
      {
        id: 1,
        call: { type: "some_future_event", args: {} } as unknown as TimelineEntry["call"],
        result: null,
      },
    ] satisfies TimelineEntry[];

    expect(() => render(<ToolTimeline entries={entries} />)).not.toThrow();
    expect(screen.getByRole("listitem")).toBeInTheDocument();
  });

  it("renders nothing for an empty timeline", () => {
    const { container } = render(<ToolTimeline entries={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
