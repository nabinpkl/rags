import { type KeyboardEvent, useRef } from "react";

import { MAP_SCOPES, type MapScope } from "@/lib/paper-map/paper-map-data";
import { cn } from "@/lib/utils";

/** Recent months or the full catalog: two separately built maps, since
 * adding papers moves every position and regroups every theme. */
export function MapScopeTabs({
  scope,
  onChange,
}: {
  scope: MapScope;
  onChange: (scope: MapScope) => void;
}) {
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKey(e: KeyboardEvent) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = MAP_SCOPES.findIndex((s) => s.id === scope);
    const next = (i + (e.key === "ArrowRight" ? 1 : MAP_SCOPES.length - 1)) % MAP_SCOPES.length;
    onChange(MAP_SCOPES[next].id);
    tabs.current[next]?.focus();
  }

  return (
    <div role="tablist" aria-label="Map" className="flex flex-wrap gap-2">
      {MAP_SCOPES.map((s, i) => {
        const selected = s.id === scope;
        return (
          <button
            key={s.id}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(s.id)}
            onKeyDown={onKey}
            className={cn(
              "border-line text-ink-2 hover:bg-panel-hover hover:border-outline flex min-h-10 items-center rounded-md border px-4 py-1.5 text-[16px] transition-colors motion-reduce:transition-none",
              selected && "border-teal-ink bg-teal-soft text-ink font-semibold",
            )}
          >
            {s.label}
          </button>
        );
      })}
    </div>
  );
}
