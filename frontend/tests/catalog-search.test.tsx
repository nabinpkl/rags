import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CatalogSearch } from "@/components/catalog/catalog-search";

describe("CatalogSearch", () => {
  it("commits on a pause, not on every keystroke", () => {
    vi.useFakeTimers();
    const onCommit = vi.fn();
    render(<CatalogSearch value="" onCommit={onCommit} />);

    const box = screen.getByLabelText("Search titles and abstracts");
    fireEvent.change(box, { target: { value: "dif" } });
    fireEvent.change(box, { target: { value: "diffusion" } });
    expect(onCommit).not.toHaveBeenCalled();

    vi.advanceTimersByTime(400);
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith("diffusion");
    vi.useRealTimers();
  });

  it("takes a query that arrived from outside, which is how a pasted link works", () => {
    const { rerender } = render(<CatalogSearch value="" onCommit={vi.fn()} />);

    rerender(<CatalogSearch value="diffusion" onCommit={vi.fn()} />);

    expect(screen.getByLabelText("Search titles and abstracts")).toHaveValue("diffusion");
  });

  it("clears to empty text, and says so upstream", () => {
    vi.useFakeTimers();
    const onCommit = vi.fn();
    render(<CatalogSearch value="diffusion" onCommit={onCommit} />);

    fireEvent.click(screen.getByLabelText("Clear search"));
    vi.advanceTimersByTime(400);

    expect(onCommit).toHaveBeenCalledWith("");
    vi.useRealTimers();
  });
});
