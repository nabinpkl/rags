import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MapScopeTabs } from "@/components/paper-map/map-scope-tabs";

describe("MapScopeTabs", () => {
  it("marks the current map and switches on click and arrow keys", () => {
    const onChange = vi.fn();
    render(<MapScopeTabs scope="recent" onChange={onChange} />);
    const [recent, full] = screen.getAllByRole("tab");
    expect(recent).toHaveTextContent("Recent months");
    expect(recent).toHaveAttribute("aria-selected", "true");
    fireEvent.click(full);
    expect(onChange).toHaveBeenLastCalledWith("full");
    fireEvent.keyDown(recent, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith("full");
  });
});
