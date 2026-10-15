import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ThemeList } from "@/components/paper-map/theme-list";
import type { MapSelection } from "@/lib/paper-map/paper-map-data";

const groups = [
  { name: "robotics · world models", size: 700, cx: 0, cy: 0 },
  { name: "speech · audio", size: 500, cx: 1, cy: 1 },
];
const themes = [
  { name: "vla · action · robot", size: 472, cx: 0, cy: 0, top_category: "cs.RO", group: 0 },
  { name: "speech · asr", size: 500, cx: 1, cy: 1, top_category: "cs.SD", group: 1 },
  { name: "jepa · world models", size: 158, cx: 0, cy: 0, top_category: "cs.LG", group: 0 },
];
const c: [number, number, number] = [10, 20, 30];

function list(selection: MapSelection, onSelect = vi.fn()) {
  return render(
    <ThemeList
      groups={groups}
      themes={themes}
      groupColors={[c, c]}
      themeColors={[c, c, c]}
      selection={selection}
      onSelect={onSelect}
    />,
  );
}

describe("ThemeList", () => {
  it("lists groups with counts and keeps their themes folded", () => {
    list(null);
    const rows = screen.getAllByRole("button");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("robotics · world models");
    expect(rows[0]).toHaveTextContent("700");
    expect(rows[0]).toHaveAttribute("aria-expanded", "false");
  });

  it("opens a selected group onto its own themes only", () => {
    list({ kind: "group", index: 0 });
    expect(screen.getByText("vla · action · robot")).toBeInTheDocument();
    expect(screen.getByText("jepa · world models")).toBeInTheDocument();
    expect(screen.queryByText("speech · asr")).not.toBeInTheDocument();
  });

  it("selects a theme, and a second press goes back to its group", () => {
    const onSelect = vi.fn();
    const { rerender } = list({ kind: "group", index: 0 }, onSelect);
    fireEvent.click(screen.getByText("jepa · world models"));
    expect(onSelect).toHaveBeenLastCalledWith({ kind: "theme", index: 2 });
    rerender(
      <ThemeList
        groups={groups}
        themes={themes}
        groupColors={[c, c]}
        themeColors={[c, c, c]}
        selection={{ kind: "theme", index: 2 }}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByText("jepa · world models"));
    expect(onSelect).toHaveBeenLastCalledWith({ kind: "group", index: 0 });
  });
});
