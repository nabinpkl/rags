import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Disclosure } from "@/components/benchmarks/disclosure";

describe("Disclosure", () => {
  it("starts shut and opens from its summary", () => {
    const { container } = render(
      <Disclosure title="Method" meta="14 facts">
        <p>body</p>
      </Disclosure>,
    );
    const details = container.querySelector("details");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText("14 facts")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Method"));
    expect(details).toHaveAttribute("open");
  });
});
