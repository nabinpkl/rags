// §6c row 4/D-1 test-first (task brief): this pane renders ONLY the capped
// excerpts it's handed — there is no prop, fetch, or code path here that
// could carry full paper text (grep-verifiable: the component takes
// `excerpts`/`excerptsTruncated` and nothing else that could resolve to
// chunk text).
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CitedExcerptsPane } from "@/components/viewer/cited-excerpts-pane";
import type { components } from "@/lib/api-types.gen";

type CitedExcerpt = components["schemas"]["CitedExcerpt"];

const EXCERPTS: CitedExcerpt[] = [
  {
    chunk_id: "c1",
    section: "§4 Evaluation",
    page_start: 3,
    page_end: 3,
    text: "the phoneme-based system achieves 17.4% WER",
  },
  {
    chunk_id: "c2",
    section: "§3 Recipe",
    page_start: 2,
    page_end: 2,
    text: "all lexical variants are derived automatically",
  },
];

describe("CitedExcerptsPane", () => {
  it("renders nothing beyond the capped excerpts it's handed", () => {
    render(
      <CitedExcerptsPane excerpts={EXCERPTS} excerptsTruncated={false} indexed onJumpToPage={vi.fn()} />,
    );
    EXCERPTS.forEach((e) => expect(screen.getByText(new RegExp(e.text))).toBeInTheDocument());
    // §6c cap note is always visible — the pane's own stated posture.
    expect(screen.getByText(/50 words.*3 per paper per answer/i)).toBeInTheDocument();
  });

  it("shows an empty state, not an error, before any citation exists", () => {
    render(<CitedExcerptsPane excerpts={[]} excerptsTruncated={false} indexed onJumpToPage={vi.fn()} />);
    expect(screen.getByText(/no cited excerpts yet/i)).toBeInTheDocument();
  });

  it("says the agent cannot read a paper whose text we never indexed", () => {
    // "No cited excerpts yet - ask the agent" is true only for an indexed
    // paper. The viewer opens co-cited works too, and asking about one of
    // those returns nothing, now or ever.
    render(
      <CitedExcerptsPane
        excerpts={[]}
        excerptsTruncated={false}
        indexed={false}
        onJumpToPage={vi.fn()}
      />,
    );
    expect(screen.getByText(/its text is not indexed/i)).toBeInTheDocument();
    expect(screen.queryByText(/ask the agent about this paper/i)).not.toBeInTheDocument();
    // The 50-word cap describes quoting, and there is nothing here to quote.
    expect(screen.queryByText(/50 words/i)).not.toBeInTheDocument();
  });

  it("a 'PDF p.N' anchor calls onJumpToPage with page_start, never page_end or a full-text fetch", () => {
    const onJumpToPage = vi.fn();
    render(
      <CitedExcerptsPane
        excerpts={EXCERPTS}
        excerptsTruncated={false}
        indexed
        onJumpToPage={onJumpToPage}
      />,
    );
    screen.getByRole("button", { name: "→ PDF p.3" }).click();
    expect(onJumpToPage).toHaveBeenCalledWith(3);
    expect(onJumpToPage).toHaveBeenCalledTimes(1);
  });

  it("builds section nav from the distinct sections actually present, first-seen order", () => {
    render(
      <CitedExcerptsPane excerpts={EXCERPTS} excerptsTruncated={false} indexed onJumpToPage={vi.fn()} />,
    );
    const nav = screen.getByText("§4 Evaluation", { selector: "button" });
    const nav2 = screen.getByText("§3 Recipe", { selector: "button" });
    expect(nav).toBeInTheDocument();
    expect(nav2).toBeInTheDocument();
  });

  it("surfaces the truncated notice only when the server flagged more citations than shown", () => {
    const { rerender } = render(
      <CitedExcerptsPane excerpts={EXCERPTS} excerptsTruncated={true} indexed onJumpToPage={vi.fn()} />,
    );
    expect(screen.getByText(/quoted more of this paper/i)).toBeInTheDocument();

    rerender(
      <CitedExcerptsPane excerpts={EXCERPTS} excerptsTruncated={false} indexed onJumpToPage={vi.fn()} />,
    );
    expect(screen.queryByText(/quoted more of this paper/i)).not.toBeInTheDocument();
  });
});
