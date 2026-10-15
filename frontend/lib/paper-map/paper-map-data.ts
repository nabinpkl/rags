/** The paper map's files (D20), served by Caddy from corpus/paper-map/.
 * Static files, not the API: `just paper-map` writes them and nothing at
 * request time recomputes them. */

const BASE = "/paper-map";

export type MapTheme = {
  name: string;
  size: number;
  cx: number;
  cy: number;
  top_category: string;
};

export type MapMeta = {
  version: number;
  /** Hash of points.bin + papers.json; versions their URLs. */
  digest: string;
  generated: string;
  from_month: string;
  to_month: string;
  n: number;
  unthemed: number;
  bounds: [number, number, number, number];
  themes: MapTheme[];
};

export type MapPoints = {
  n: number;
  /** Data-space coordinates, decoded from uint16. */
  x: Float32Array;
  y: Float32Array;
  /** Index into `themes`, -1 for no theme. */
  theme: Int16Array;
};

export type MapPapers = { ids: string[]; versions: string[]; titles: string[] };

export const NO_THEME = -1;
const QMAX = 65535;

/** points.bin: uint16 x[n], uint16 y[n], int16 theme[n], little-endian. */
export function decodePoints(buf: ArrayBuffer, meta: MapMeta): MapPoints {
  const n = meta.n;
  if (buf.byteLength !== n * 6) {
    throw new Error(`points.bin is ${buf.byteLength} bytes; ${n} papers need ${n * 6}`);
  }
  const view = new DataView(buf);
  const [x0, y0, x1, y1] = meta.bounds;
  const x = new Float32Array(n);
  const y = new Float32Array(n);
  const theme = new Int16Array(n);
  for (let i = 0; i < n; i++) {
    x[i] = x0 + (view.getUint16(2 * i, true) / QMAX) * (x1 - x0);
    y[i] = y0 + (view.getUint16(2 * n + 2 * i, true) / QMAX) * (y1 - y0);
    theme[i] = view.getInt16(4 * n + 2 * i, true);
  }
  return { n, x, y, theme };
}

async function get(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${BASE}/${path}`, init);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res;
}

export async function fetchMap(): Promise<{ meta: MapMeta; points: MapPoints }> {
  // map.json always revalidates; the files it names are fetched by digest,
  // so a rebuild can never pair new meta with cached old points.
  const meta = (await (await get("map.json", { cache: "no-cache" })).json()) as MapMeta;
  const points = decodePoints(await (await get(`points.bin?v=${meta.digest}`)).arrayBuffer(), meta);
  return { meta, points };
}

export async function fetchPapers(digest: string): Promise<MapPapers> {
  return (await (await get(`papers.json?v=${digest}`)).json()) as MapPapers;
}
