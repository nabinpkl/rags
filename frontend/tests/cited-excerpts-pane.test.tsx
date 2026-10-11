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
      <CitedExcerptsPane excerpts={EXCERPTS} excerptsTruncated={false} onJumpToPage={vi.fn()} />,
    );
    EXCERPTS.forEach((e) => expect(screen.getByText(new RegExp(e.text))).toBeInTheDocument());
    expect(screen.getAllByRole("listitem")).toHaveLength(EXCERPTS.length);
  });

  it("a 'PDF p.N' anchor calls onJumpToPage with page_start, never page_end or a full-text fetch", () => {
    const onJumpToPage = vi.fn();
    render(
      <CitedExcerptsPane
        excerpts={EXCERPTS}
        excerptsTruncated={false}
        onJumpToPage={onJumpToPage}
      />,
    );
    screen.getByRole("button", { name: "→ PDF p.3" }).click();
    expect(onJumpToPage).toHaveBeenCalledWith(3);
    expect(onJumpToPage).toHaveBeenCalledTimes(1);
  });

  it("builds section nav from the distinct sections actually present", () => {
    render(
      <CitedExcerptsPane excerpts={EXCERPTS} excerptsTruncated={false} onJumpToPage={vi.fn()} />,
    );
    const nav = screen.getByText("§4 Evaluation", { selector: "button" });
    const nav2 = screen.getByText("§3 Recipe", { selector: "button" });
    expect(nav).toBeInTheDocument();
    expect(nav2).toBeInTheDocument();
  });

  it("skips the section nav when every excerpt is from one section", () => {
    render(
      <CitedExcerptsPane
        excerpts={[EXCERPTS[0]]}
        excerptsTruncated={false}
        onJumpToPage={vi.fn()}
      />,
    );
    expect(screen.queryByRole("navigation", { name: "Sections" })).not.toBeInTheDocument();
  });

  it("surfaces the truncated notice only when the server flagged more citations than shown", () => {
    const { rerender } = render(
      <CitedExcerptsPane excerpts={EXCERPTS} excerptsTruncated={true} onJumpToPage={vi.fn()} />,
    );
    expect(screen.getByText(/more was quoted/i)).toBeInTheDocument();

    rerender(
      <CitedExcerptsPane excerpts={EXCERPTS} excerptsTruncated={false} onJumpToPage={vi.fn()} />,
    );
    expect(screen.queryByText(/more was quoted/i)).not.toBeInTheDocument();
  });
});
