import { ChevronRight } from "lucide-react";

import type { MapGroup, MapSelection, MapTheme } from "@/lib/paper-map/paper-map-data";
import { cssRgb, type RGB } from "@/lib/paper-map/theme-colors";
import { cn } from "@/lib/utils";

/** Umbrella groups, largest first; picking one flies the map to it, dims the
 * rest and opens its themes underneath. The same names the map draws, as
 * real text. */
export function ThemeList({
  groups,
  themes,
  groupColors,
  themeColors,
  selection,
  onSelect,
}: {
  groups: MapGroup[];
  themes: MapTheme[];
  groupColors: RGB[];
  themeColors: RGB[];
  selection: MapSelection;
  onSelect: (selection: MapSelection) => void;
}) {
  const openGroup =
    selection?.kind === "group"
      ? selection.index
      : selection?.kind === "theme"
        ? themes[selection.index].group
        : null;

  return (
    <ul className="flex flex-col gap-0.5" aria-label="Themes">
      {groups.map((g, gi) => {
        const open = openGroup === gi;
        const on = selection?.kind === "group" && selection.index === gi;
        return (
          <li key={g.name + gi}>
            <Row
              name={g.name}
              size={g.size}
              color={groupColors[gi]}
              pressed={on}
              expanded={open}
              strong
              onClick={() => onSelect(on ? null : { kind: "group", index: gi })}
            />
            {open && (
              <ul className="border-line mt-0.5 mb-1.5 ml-4 flex flex-col gap-0.5 border-l pl-2">
                {themes.map((t, ti) => {
                  if (t.group !== gi) return null;
                  const tOn = selection?.kind === "theme" && selection.index === ti;
                  return (
                    <li key={t.name + ti}>
                      <Row
                        name={t.name}
                        size={t.size}
                        color={themeColors[ti]}
                        pressed={tOn}
                        onClick={() =>
                          onSelect(
                            tOn ? { kind: "group", index: gi } : { kind: "theme", index: ti },
                          )
                        }
                      />
                    </li>
                  );
                })}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Row({
  name,
  size,
  color,
  pressed,
  expanded,
  strong,
  onClick,
}: {
  name: string;
  size: number;
  color: RGB;
  pressed: boolean;
  expanded?: boolean;
  strong?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-expanded={expanded}
      onClick={onClick}
      className={cn(
        "hover:bg-panel-hover text-ink grid min-h-10 w-full items-center gap-2.5 rounded px-2.5 py-1.5 text-left text-[16px] leading-snug transition-colors motion-reduce:transition-none",
        expanded === undefined ? "grid-cols-[12px_1fr_auto]" : "grid-cols-[12px_1fr_auto_16px]",
        pressed && "bg-teal-soft",
        strong && "font-medium",
      )}
    >
      <span aria-hidden className="size-3 rounded-sm" style={{ background: cssRgb(color) }} />
      <span className="min-w-0">{name}</span>
      <span className="text-muted font-mono text-[14px] font-normal tabular-nums">
        {size.toLocaleString("en")}
      </span>
      {expanded !== undefined && (
        <ChevronRight
          aria-hidden
          className={cn(
            "text-muted size-4 transition-transform motion-reduce:transition-none",
            expanded && "rotate-90",
          )}
        />
      )}
    </button>
  );
}
