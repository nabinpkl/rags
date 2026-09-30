// Contrast guard for the palette in app/globals.css.
//
// Every text colour the UI sets on a surface is listed below as a pair, and
// each pair is measured in both themes against WCAG AA. A token edit that
// drops a pair under its floor fails here rather than on a reader's screen:
// the 2026-09-30 audit found three pairs (canvas metadata, the agent panel's
// grey, its error text) that had drifted under 4.5:1 without anyone seeing.
//
// The pairs only protect colours that come from tokens, so the second test
// refuses a hard-coded hex colour in a component: `text-[#abc]` would never
// reach this table.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = resolve(__dirname, "..");
const CSS = readFileSync(join(ROOT, "app/globals.css"), "utf8");

/** The declarations inside the first block opened by `selector {`. */
function block(selector: string): Map<string, string> {
  const start = CSS.indexOf(`${selector} {`);
  if (start === -1) throw new Error(`globals.css has no "${selector}" block`);
  let depth = 0;
  let end = start;
  for (let i = CSS.indexOf("{", start); i < CSS.length; i++) {
    if (CSS[i] === "{") depth++;
    if (CSS[i] === "}" && --depth === 0) {
      end = i;
      break;
    }
  }
  const body = CSS.slice(start, end).replace(/\/\*[\s\S]*?\*\//g, "");
  const tokens = new Map<string, string>();
  for (const match of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    tokens.set(match[1], match[2].trim());
  }
  return tokens;
}

const THEME = block("@theme inline");
const LIGHT = block(":root");
const DARK = new Map([...LIGHT, ...block(".dark")]);

/** A Tailwind colour name ("machine-muted") to its hex value in one theme. */
function color(name: string, palette: Map<string, string>): string {
  let value = THEME.get(`--color-${name}`);
  for (let hops = 0; value?.startsWith("var("); hops++) {
    if (hops > 4) throw new Error(`--color-${name} does not resolve`);
    const ref = value.slice(4, -1).trim();
    value = palette.get(ref) ?? THEME.get(ref);
  }
  if (!value || !/^#[0-9a-f]{6}$/i.test(value)) {
    throw new Error(`--color-${name} is not a 6-digit hex colour: ${value}`);
  }
  return value;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [text, surface, floor]. 4.5 is AA for body text, which is every pair here:
// the app's small mono labels (9.5-12px) never qualify as large text.
const AA = 4.5;
const PAIRS: [string, string, number][] = [
  // The catalog, the rail and the reader: text on the canvas and on panels.
  ["ink", "paper", AA],
  ["ink", "panel", AA],
  ["ink-2", "paper", AA],
  ["ink-2", "panel", AA],
  ["muted", "paper", AA],
  ["muted", "panel", AA],
  ["muted", "panel-hover", AA],
  ["teal-ink", "paper", AA],
  ["teal-ink", "panel", AA],
  ["teal-ink", "teal-soft", AA],
  ["teal-ink", "teal-soft-strong", AA],
  // The agent panel.
  ["machine-text", "machine", AA],
  ["machine-text", "machine-2", AA],
  ["machine-muted", "machine", AA],
  ["machine-muted", "machine-2", AA],
  ["machine-accent", "machine", AA],
  ["machine-accent", "machine-2", AA],
  ["machine-amber", "machine", AA],
  ["machine-rust", "machine", AA],
  // Fixed in both themes.
  ["teal-deep-label", "teal-deep", AA],
  ["teal-deep-label", "teal-deep-hover", AA],
  ["amber-ink", "amber-soft", AA],
  ["surround-text", "surround", AA],
];

// A card's outline against the canvas it sits on. Not a WCAG floor (the
// card is also told apart by its fill and its text), but a house one: at
// 1.4:1 the light theme's cards washed out, and 1.7 is the least the owner
// signed off on seeing.
const EDGE = 1.7;
const EDGES: [string, string, number][] = [["outline", "paper", EDGE]];

describe("globals.css palette contrast", () => {
  for (const [theme, palette] of [
    ["light", LIGHT],
    ["dark", DARK],
  ] as const) {
    it.each([...PAIRS, ...EDGES])(`${theme}: %s on %s reaches %s:1`, (text, surface, floor) => {
      const ratio = contrast(color(text, palette), color(surface, palette));
      expect(ratio, `${text} on ${surface} is ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(floor);
    });
  }
});

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(tsx|ts)$/.test(name) ? [path] : [];
  });
}

describe("colour literals", () => {
  it("leaves every component colour to a token, so the pairs above cover it", () => {
    const offenders = [join(ROOT, "components"), join(ROOT, "app")]
      .flatMap(sources)
      .flatMap((path) =>
        readFileSync(path, "utf8")
          .split("\n")
          .map((line, i) => ({ line, at: `${path.slice(ROOT.length + 1)}:${i + 1}` }))
          .filter(({ line }) => /-\[#[0-9a-fA-F]{3,8}\]/.test(line))
          .map(({ at }) => at),
      );
    expect(offenders).toEqual([]);
  });
});
