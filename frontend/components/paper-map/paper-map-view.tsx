"use client";

import { useQuery } from "@tanstack/react-query";
import { Minus, Plus, RotateCcw } from "lucide-react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
import { type ReactNode, useMemo, useRef, useState } from "react";

import type { PaperMapHandle } from "@/components/paper-map/paper-map-canvas";
import { PaperCard } from "@/components/paper-map/paper-card";
import { ThemeList } from "@/components/paper-map/theme-list";
import { fetchMap, fetchPapers, NO_THEME } from "@/lib/paper-map/paper-map-data";
import { themeColors } from "@/lib/paper-map/theme-colors";

// deck.gl needs a browser (WebGL, window); the static export renders the
// page shell without it.
const PaperMapCanvas = dynamic(
  () => import("@/components/paper-map/paper-map-canvas").then((m) => m.PaperMapCanvas),
  { ssr: false },
);

const DARK_BRIGHTNESS = 0.4;

function MapButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="bg-panel border-line text-ink hover:bg-panel-hover flex size-10 items-center justify-center rounded border shadow-sm transition-colors disabled:opacity-50 motion-reduce:transition-none"
    >
      {children}
    </button>
  );
}

export function PaperMapView() {
  const map = useQuery({ queryKey: ["paper-map"], queryFn: fetchMap, staleTime: Infinity });
  const papers = useQuery({
    queryKey: ["paper-map-papers", map.data?.meta.digest],
    queryFn: () => fetchPapers(map.data?.meta.digest ?? ""),
    staleTime: Infinity,
    enabled: map.isSuccess,
  });
  const { resolvedTheme } = useTheme();
  const canvas = useRef<PaperMapHandle>(null);

  const [hideUnthemed, setHideUnthemed] = useState(false);
  const [brightness, setBrightness] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const [picked, setPicked] = useState<number | null>(null);

  const meta = map.data?.meta;
  const points = map.data?.points;
  const colors = useMemo(() => themeColors(meta?.themes.length ?? 0), [meta]);
  const level = brightness ?? (resolvedTheme === "dark" ? DARK_BRIGHTNESS : 0);

  if (map.isError) {
    return (
      <p className="text-ink text-[16px]" role="alert">
        The map did not load: {map.error.message}
      </p>
    );
  }

  const themeName = (i: number) => {
    const t = points?.theme[i] ?? NO_THEME;
    return t === NO_THEME ? "No theme" : (meta?.themes[t].name ?? "");
  };

  function select(i: number | null) {
    setSelected(i);
    if (i === null) canvas.current?.reset();
    else canvas.current?.flyTo(i);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="border-line bg-panel relative h-[min(76dvh,880px)] min-h-[440px] overflow-hidden rounded-lg border">
        {meta && points ? (
          <PaperMapCanvas
            ref={canvas}
            meta={meta}
            points={points}
            colors={colors}
            hideUnthemed={hideUnthemed}
            brightness={level}
            selectedTheme={selected}
            colorScheme={resolvedTheme}
            onHover={(i, x, y) => setHover(i < 0 ? null : { i, x, y })}
            onPick={(i) => setPicked(i < 0 ? null : i)}
          />
        ) : (
          <p className="text-muted absolute inset-0 grid place-items-center text-[16px]">
            Loading the map
          </p>
        )}

        <div className="absolute top-3 left-3 z-10 flex flex-col gap-1.5">
          <MapButton label="Zoom in" disabled={!meta} onClick={() => canvas.current?.zoomBy(1.6)}>
            <Plus className="size-4" aria-hidden />
          </MapButton>
          <MapButton
            label="Zoom out"
            disabled={!meta}
            onClick={() => canvas.current?.zoomBy(1 / 1.6)}
          >
            <Minus className="size-4" aria-hidden />
          </MapButton>
          <MapButton label="Reset view" disabled={!meta} onClick={() => select(null)}>
            <RotateCcw className="size-4" aria-hidden />
          </MapButton>
        </div>

        {hover && (
          <div
            role="tooltip"
            className="bg-panel border-line pointer-events-none absolute z-10 max-w-[360px] rounded-md border px-3 py-2 shadow-md"
            style={{ left: hover.x + 14, top: hover.y + 14 }}
          >
            {papers.data && (
              <p className="text-ink text-[16px] leading-snug font-semibold">
                {papers.data.titles[hover.i]}
              </p>
            )}
            <p className="text-muted text-[14px]">{themeName(hover.i)}</p>
          </div>
        )}

        {picked !== null && papers.data && (
          <PaperCard
            arxivId={papers.data.ids[picked]}
            version={papers.data.versions[picked]}
            title={papers.data.titles[picked]}
            theme={themeName(picked)}
            onClose={() => setPicked(null)}
          />
        )}
      </div>

      <aside className="border-line bg-panel flex max-h-[min(76dvh,880px)] min-h-0 flex-col rounded-lg border">
        <div className="border-line flex flex-col gap-3 border-b p-4">
          <label className="text-ink flex min-h-8 items-center gap-2.5 text-[16px]">
            <input
              type="checkbox"
              checked={hideUnthemed}
              onChange={(e) => setHideUnthemed(e.target.checked)}
              className="accent-[var(--teal-ink)] size-4"
            />
            Hide papers with no theme
            {meta && (
              <span className="text-muted font-mono text-[14px] tabular-nums">
                {meta.unthemed.toLocaleString("en")}
              </span>
            )}
          </label>
          <label className="text-ink flex min-h-8 items-center gap-3 text-[16px]">
            Brightness
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={Math.round(level * 100)}
              onChange={(e) => setBrightness(Number(e.target.value) / 100)}
              className="accent-[var(--teal-ink)] min-w-0 flex-1"
            />
          </label>
        </div>
        <h2 className="text-muted px-4 pt-3 pb-1 text-[14px] font-semibold tracking-wide uppercase">
          Themes
        </h2>
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {meta && (
            <ThemeList themes={meta.themes} colors={colors} selected={selected} onSelect={select} />
          )}
        </div>
      </aside>
    </div>
  );
}
