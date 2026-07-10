"use client";

import { useEffect, useState } from "react";
import { useViewerStore } from "@/stores/viewer-store";

const DEBOUNCE_MS = 300;

/** Semantic + keyword search box hitting `/api/papers?q=` (via
 * use-papers-query.ts's usePapersQuery, HybridSearch under the hood — D8's
 * fail-soft BM25 degrade already covers "keyword" as a fallback, not a
 * separate mode, decisions.md #27 Fill-in 1). Debounces local edits into the
 * store so every keystroke doesn't push a URL change / refetch. */
export function CorpusSearchBar() {
  const q = useViewerStore((state) => state.q);
  const setFilters = useViewerStore((state) => state.setFilters);
  const [value, setValue] = useState(q);
  const [syncedQ, setSyncedQ] = useState(q);

  // External q changes (URL nav, reset()) resync the input — adjusted
  // during render ("Adjusting state when a prop changes", React docs), not
  // in an Effect: a synchronous setState inside an Effect body is a lint
  // error (react-hooks/set-state-in-effect) and costs an extra commit.
  if (q !== syncedQ) {
    setSyncedQ(q);
    setValue(q);
  }

  useEffect(() => {
    if (value === q) return;
    const timer = setTimeout(() => setFilters({ q: value }), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value, q, setFilters]);

  return (
    <input
      type="search"
      value={value}
      onChange={(event) => setValue(event.target.value)}
      placeholder="Search the corpus — semantic + keyword"
      aria-label="Search corpus"
      className="border-line bg-paper text-ink placeholder:text-muted w-full max-w-[420px] rounded px-3 py-1.5 text-[13.5px] outline-none"
    />
  );
}
