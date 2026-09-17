import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TOP_TOPICS, TopicFilter } from "@/components/catalog/topic-filter";
import type { CatalogBucket } from "@/lib/api-client";

const NAMED: CatalogBucket[] = [
  { value: "cs.CL", papers: 36_956, name: "Computation and Language" },
  { value: "cs.CV", papers: 5_635, name: "Computer Vision and Pattern Recognition" },
  { value: "cs.LG", papers: 5_051, name: "Machine Learning" },
];

// Twelve buckets: nine on show, three folded.
const MANY: CatalogBucket[] = [
  ...NAMED,
  ...Array.from({ length: 9 }, (_, i) => ({
    value: `math.X${i}`,
    papers: 100 - i,
    name: null,
  })),
];

function topics() {
  return within(screen.getByRole("list", { name: "Topic" }));
}

describe("TopicFilter", () => {
  it("names a topic, and says its count both short and in full", () => {
    render(<TopicFilter buckets={NAMED} selected={null} onSelect={() => {}} />);

    const row = topics().getByRole("button", { name: /Computation and Language/ });
    expect(row).toHaveTextContent("37K");
    expect(row).toHaveAccessibleName(/36,956 papers/);
    expect(row).toHaveAttribute("title", "Computation and Language (cs.CL)");
  });

  it("shows a code with no name as the code", () => {
    render(<TopicFilter buckets={MANY.slice(0, 4)} selected={null} onSelect={() => {}} />);

    expect(topics().getByRole("button", { name: /^math\.X0/ })).toBeInTheDocument();
  });

  it("selects a topic, and clears it when pressed again", () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <TopicFilter buckets={NAMED} selected={null} onSelect={onSelect} />,
    );
    fireEvent.click(topics().getByRole("button", { name: /Machine Learning/ }));
    expect(onSelect).toHaveBeenLastCalledWith("cs.LG");

    rerender(<TopicFilter buckets={NAMED} selected="cs.LG" onSelect={onSelect} />);
    const row = topics().getByRole("button", { name: /Machine Learning/ });
    expect(row).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(row);
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("folds the tail under Others with what it holds, and opens it", () => {
    render(<TopicFilter buckets={MANY} selected={null} onSelect={() => {}} />);

    expect(topics().getAllByRole("button", { pressed: false })).toHaveLength(TOP_TOPICS);
    const others = topics().getByRole("button", { name: /Others \(3\)/ });
    // The three folded buckets hold 94 + 93 + 92 papers.
    expect(others).toHaveAccessibleName(/279 papers/);

    fireEvent.click(others);
    expect(topics().getAllByRole("button", { pressed: false })).toHaveLength(12);
    expect(topics().getByRole("button", { name: "Fewer topics" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("keeps a selected topic from the tail on screen while the tail is folded", () => {
    render(<TopicFilter buckets={MANY} selected="math.X8" onSelect={() => {}} />);

    expect(topics().getByRole("button", { name: /^math\.X8/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("renders nothing until the facets arrive", () => {
    render(<TopicFilter buckets={undefined} selected={null} onSelect={() => {}} />);

    expect(screen.queryByRole("list", { name: "Topic" })).not.toBeInTheDocument();
  });
});
