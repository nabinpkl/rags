import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThemeList } from "@/components/paper-map/theme-list";

const themes = [
  { name: "robot · action · world", size: 4144, cx: 0, cy: 0, top_category: "cs.RO" },
  { name: "speech · audio · speaker", size: 565, cx: 1, cy: 1, top_category: "cs.SD" },
];
const colors: [number, number, number][] = [
  [200, 50, 50],
  [50, 200, 50],
];

describe("ThemeList", () => {
  it("lists each theme with its paper count", () => {
    render(<ThemeList themes={themes} colors={colors} selected={null} onSelect={() => {}} />);
    const rows = screen.getAllByRole("button");
    expect(rows[0]).toHaveTextContent("robot · action · world");
    expect(rows[0]).toHaveTextContent("4,144");
  });

  it("selects a theme, and a second press clears it", () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <ThemeList themes={themes} colors={colors} selected={null} onSelect={onSelect} />,
    );
    fireEvent.click(screen.getByText("speech · audio · speaker"));
    expect(onSelect).toHaveBeenLastCalledWith(1);
    rerender(<ThemeList themes={themes} colors={colors} selected={1} onSelect={onSelect} />);
    const row = screen.getByRole("button", { pressed: true });
    fireEvent.click(row);
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });
});
