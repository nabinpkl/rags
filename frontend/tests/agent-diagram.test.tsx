import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AGENT_TOOLS, AgentDiagram } from "@/components/architecture/agent-diagram";

describe("AgentDiagram", () => {
  it("lists every agent tool", () => {
    render(<AgentDiagram />);
    for (const tool of AGENT_TOOLS) expect(screen.getByText(tool)).toBeInTheDocument();
  });

  it("shows the budget gate before the model and the quote caps on the answer", () => {
    render(<AgentDiagram />);
    expect(screen.getByText("Budget gate")).toBeInTheDocument();
    expect(screen.getByText(/quotes ≤ 50 words, ≤ 3 per paper/)).toBeInTheDocument();
  });
});
