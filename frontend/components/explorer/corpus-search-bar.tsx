"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { useViewerStore } from "@/stores/viewer-store";

const DEBOUNCE_MS = 300;

/** Semantic + keyword search box hitting `/api/papers?q=` (via
 * use-papers-query.ts's usePapersQuery, HybridSearch under the hood — D8's
 * fail-soft BM25 degrade already covers "keyword" as a fallback, not a
 * separate mode, DECISIONS.md #27 Fill-in 1). Debounces local edits into the
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
    // Its own full-width row below `sm:` (the header wraps): sharing a line
    // with the "Corpus" heading at 390px leaves ~120px of input.
    <div className="relative w-full max-w-[420px] sm:w-auto sm:flex-1">
      {/* The field sits beside a serif heading, so it has to announce itself
          as a control rather than as that heading's subtitle: a magnifier, a
          border, and a surface a step off the page it sits on. Filled and
          bordered in both themes — `bg-panel` reads lighter than `--paper` in
          light and darker-but-distinct in dark. */}
      <Search
        aria-hidden="true"
        className="text-muted pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2"
      />
      <input
        type="search"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search papers…"
        aria-label="Search papers"
        // 16px text below `sm:` — iOS Safari zooms the page on a smaller
        // focused font and never zooms back out.
        className="border-line bg-panel text-ink placeholder:text-muted w-full rounded border py-2 pr-3 pl-8 text-[16px] sm:py-1.5 sm:text-[13.5px]"
      />
    </div>
  );
}
