import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RetrievalDiagram } from "@/components/architecture/retrieval-diagram";

describe("RetrievalDiagram", () => {
  it("draws the depths it is given, not fixed numbers", () => {
    render(<RetrievalDiagram poolK={40} k={8} chunkTokens={1000} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(/40 chunks each.*top 8/);
    expect(screen.getAllByText("40")).toHaveLength(3);
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText(/1,000-TOKEN CHUNKS/)).toBeInTheDocument();
  });

  it("names the rerank stage", () => {
    render(<RetrievalDiagram poolK={50} k={10} chunkTokens={1000} />);
    expect(screen.getByText("Reranker")).toBeInTheDocument();
  });
});
