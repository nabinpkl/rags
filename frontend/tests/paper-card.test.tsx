import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PaperCard } from "@/components/paper-map/paper-card";

describe("PaperCard", () => {
  it("links to the version-pinned arXiv page and closes", () => {
    const onClose = vi.fn();
    render(
      <PaperCard
        arxivId="2607.00001"
        version="v2"
        title="A paper"
        theme="robot · action · world"
        onClose={onClose}
      />,
    );
    expect(screen.getByRole("link", { name: /open on arxiv/i })).toHaveAttribute(
      "href",
      "https://arxiv.org/abs/2607.00001v2",
    );
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });
});
