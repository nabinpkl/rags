import { cn } from "@/lib/utils";
import type { MapTheme } from "@/lib/paper-map/paper-map-data";
import { cssRgb, type RGB } from "@/lib/paper-map/theme-colors";

/** Every theme, largest first; picking one flies the map to it and dims the
 * rest. The same names the map draws, as real text. */
export function ThemeList({
  themes,
  colors,
  selected,
  onSelect,
}: {
  themes: MapTheme[];
  colors: RGB[];
  selected: number | null;
  onSelect: (index: number | null) => void;
}) {
  return (
    <ul className="flex flex-col gap-0.5" aria-label="Themes">
      {themes.map((t, i) => {
        const on = selected === i;
        return (
          <li key={t.name + i}>
            <button
              type="button"
              aria-pressed={on}
              onClick={() => onSelect(on ? null : i)}
              className={cn(
                "hover:bg-panel-hover grid min-h-10 w-full grid-cols-[12px_1fr_auto] items-center gap-2.5 rounded px-2.5 py-1.5 text-left text-[16px] leading-snug transition-colors motion-reduce:transition-none",
                on ? "bg-teal-soft text-ink" : "text-ink",
              )}
            >
              <span
                aria-hidden
                className="size-3 rounded-sm"
                style={{ background: cssRgb(colors[i]) }}
              />
              <span className="min-w-0">{t.name}</span>
              <span className="text-muted font-mono text-[14px] tabular-nums">
                {t.size.toLocaleString("en")}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
