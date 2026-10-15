"use client";

import { Deck, LinearInterpolator, OrthographicView } from "@deck.gl/core";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { type Ref, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef } from "react";

import { fitView, type MapViewState, project, themeBox } from "@/lib/paper-map/fit-view";
import {
  type MapMeta,
  type MapPoints,
  type MapSelection,
  NO_THEME,
} from "@/lib/paper-map/paper-map-data";
import {
  type Box,
  LABEL_STYLE,
  type LabelKind,
  labelText,
  placeLabels,
  themeMinLevel,
} from "@/lib/paper-map/place-labels";
import { lighten, parseColor, type RGB, UNTHEMED_RGB } from "@/lib/paper-map/theme-colors";

export type PaperMapHandle = {
  zoomBy: (factor: number) => void;
  reset: () => void;
  flyTo: (selection: NonNullable<MapSelection>) => void;
};

type Props = {
  ref?: Ref<PaperMapHandle>;
  meta: MapMeta;
  points: MapPoints;
  colors: RGB[];
  hideUnthemed: boolean;
  /** 0..1: lightens colours and raises opacity, for dark backgrounds. */
  brightness: number;
  selection: MapSelection;
  /** Changes when the site theme does, so labels re-read the page tokens. */
  colorScheme: string | undefined;
  onHover: (index: number, x: number, y: number) => void;
  onPick: (index: number) => void;
};

const THEMED_ALPHA = 200;
const UNTHEMED_ALPHA = 90;
const DIMMED = 0.2;

/** The map itself: every paper as a GPU point, theme labels as GPU text in
 * the same canvas, so labels never drift from their points while panning.
 * deck.gl is driven imperatively; React owns the inputs, not the frames. */
function inSelection(meta: MapMeta, sel: NonNullable<MapSelection>, theme: number): boolean {
  if (theme === NO_THEME) return false;
  return sel.kind === "theme" ? theme === sel.index : meta.themes[theme].group === sel.index;
}

export function PaperMapCanvas(props: Props) {
  const { ref, meta, points, colors, hideUnthemed, brightness, selection } = props;
  const hostRef = useRef<HTMLDivElement>(null);
  const deckRef = useRef<Deck<OrthographicView> | null>(null);
  const viewRef = useRef<MapViewState | null>(null);
  const homeRef = useRef<MapViewState | null>(null);
  const propsRef = useRef(props);

  const positions = useMemo(() => {
    const p = new Float32Array(points.n * 2);
    for (let i = 0; i < points.n; i++) {
      p[2 * i] = points.x[i];
      p[2 * i + 1] = points.y[i];
    }
    return p;
  }, [points]);

  const fill = useMemo(() => {
    const out = new Uint8Array(points.n * 4);
    const lit = colors.map((c) => lighten(c, brightness));
    const grey = lighten(UNTHEMED_RGB, brightness);
    for (let i = 0; i < points.n; i++) {
      const t = points.theme[i];
      const themed = t !== NO_THEME;
      let a = themed ? THEMED_ALPHA : hideUnthemed ? 0 : UNTHEMED_ALPHA;
      if (selection && !inSelection(meta, selection, t)) a = Math.round(a * DIMMED);
      const c = themed ? lit[t] : grey;
      out.set([c[0], c[1], c[2], a], 4 * i);
    }
    return out;
  }, [meta, points, colors, brightness, hideUnthemed, selection]);

  const fillRef = useRef(fill);

  function size(): [number, number] {
    const el = hostRef.current;
    return [el?.clientWidth ?? 1, el?.clientHeight ?? 1];
  }

  function layers() {
    const p = propsRef.current;
    const css = getComputedStyle(document.documentElement);
    const ink = parseColor(css.getPropertyValue("--ink"));
    const halo = parseColor(css.getPropertyValue("--paper"));
    const fontFamily = getComputedStyle(document.body).fontFamily;
    const view = viewRef.current;
    const home = homeRef.current;
    if (!view || !home) return [];
    const [w, h] = size();
    const levels = view.zoom - home.zoom;
    // Groups at every zoom, placed first so no theme covers its parent;
    // themes from THEME_ZOOM on, in the space the groups leave.
    const taken: Box[] = [];
    const candidates = (
      items: { name: string; size: number; cx: number; cy: number }[],
      kind: LabelKind,
    ) =>
      items.map((t, index) => {
        const [x, y] = project(view, w, h, t.cx, t.cy);
        const minLevel = kind === "group" ? 0 : themeMinLevel(index);
        return { index, name: labelText(t.name, kind), size: t.size, px: x, py: y, minLevel };
      });
    const groupCands = candidates(p.meta.groups, "group");
    const groupsShown = placeLabels(groupCands, levels, w, h, "group", taken);
    const themeCands = candidates(p.meta.themes, "theme");
    const themesShown = placeLabels(themeCands, levels, w, h, "theme", taken);
    const ink2 = parseColor(css.getPropertyValue("--ink-2"));
    const textLayer = (id: string, cands: typeof groupCands, shown: number[], kind: LabelKind) =>
      new TextLayer({
        id,
        data: shown.map((i) => ({
          ...cands[i],
          ...(kind === "group" ? p.meta.groups[i] : p.meta.themes[i]),
          text: cands[i].name,
        })),
        getPosition: (t: { cx: number; cy: number }) => [t.cx, t.cy],
        getText: (t: { text: string }) => t.text,
        getSize: LABEL_STYLE[kind].px,
        sizeUnits: "pixels",
        getColor: kind === "group" ? ink : ink2,
        fontFamily,
        fontWeight: LABEL_STYLE[kind].weight,
        fontSettings: { sdf: true },
        outlineWidth: 3,
        outlineColor: halo,
        characterSet: "auto",
      });
    return [
      new ScatterplotLayer({
        id: "papers",
        data: {
          length: p.points.n,
          attributes: {
            getPosition: { value: positions, size: 2 },
            getFillColor: { value: fillRef.current, size: 4 },
          },
        },
        radiusUnits: "pixels",
        getRadius: 1.2,
        radiusMinPixels: 1,
        opacity: Math.min(1, 0.35 + 0.22 * Math.max(0, levels) + 0.65 * p.brightness),
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 255],
      }),
      textLayer("theme-labels", themeCands, themesShown, "theme"),
      textLayer("group-labels", groupCands, groupsShown, "group"),
    ];
  }

  function render() {
    deckRef.current?.setProps({ layers: layers() });
  }

  function go(view: MapViewState) {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const next = {
      ...view,
      transitionDuration: reduce ? 0 : 400,
      transitionInterpolator: new LinearInterpolator(["target", "zoom"]),
    };
    viewRef.current = view;
    deckRef.current?.setProps({ initialViewState: next, layers: layers() });
  }

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const { bounds } = propsRef.current.meta;
    const home = fitView(
      { minX: bounds[0], minY: bounds[1], maxX: bounds[2], maxY: bounds[3] },
      host.clientWidth,
      host.clientHeight,
    );
    homeRef.current = home;
    viewRef.current = home;
    const deck = new Deck<OrthographicView>({
      parent: host,
      views: new OrthographicView({ flipY: false }),
      initialViewState: home,
      controller: { inertia: 300 },
      pickingRadius: 6,
      onViewStateChange: ({ viewState }) => {
        viewRef.current = viewState as unknown as MapViewState;
        deck.setProps({ layers: layers() });
        return viewState;
      },
      onResize: () => render(),
      onHover: ({ index, x, y, layer }) =>
        propsRef.current.onHover(layer?.id === "papers" ? index : -1, x, y),
      onClick: ({ index, layer }) => propsRef.current.onPick(layer?.id === "papers" ? index : -1),
      getCursor: ({ isDragging, isHovering }) =>
        isDragging ? "grabbing" : isHovering ? "pointer" : "grab",
      layers: [],
    });
    deckRef.current = deck;
    render();
    return () => {
      deck.finalize();
      deckRef.current = null;
    };
    // The deck lives for the component's life; inputs reach it through refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Every render hands the deck the latest inputs; layers are cheap to
  // describe and deck.gl diffs them.
  useLayoutEffect(() => {
    propsRef.current = props;
    fillRef.current = fill;
    render();
  });

  useImperativeHandle(ref, () => ({
    zoomBy: (factor) => {
      const v = viewRef.current;
      if (v) go({ target: v.target, zoom: v.zoom + Math.log2(factor) });
    },
    reset: () => {
      if (homeRef.current) go(homeRef.current);
    },
    flyTo: (sel) => {
      const box = themeBox(points.x, points.y, (i) => inSelection(meta, sel, points.theme[i]));
      const [w, h] = size();
      go(fitView(box, w, h, 0.7));
    },
  }));

  return <div ref={hostRef} className="absolute inset-0" />;
}
