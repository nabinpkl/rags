import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TurnSequence } from "@/components/architecture/turn-sequence";

describe("TurnSequence", () => {
  it("routes every search through a tool call into retrieval", () => {
    render(<TurnSequence k={10} />);
    for (const lane of ["Reader", "Claude", "Tools", "Retrieval"]) {
      expect(screen.getByText(lane)).toBeInTheDocument();
    }
    expect(screen.getByText("search_corpus")).toBeInTheDocument();
    expect(screen.getByText("fuse + rerank")).toBeInTheDocument();
    expect(screen.getByText("10 chunks")).toBeInTheDocument();
  });
});
