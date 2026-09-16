"use client";

import { Search, X } from "lucide-react";
import { useEffect, useState } from "react";

const DEBOUNCE_MS = 300;

/** The catalog's search field, at the head of the results rather than in the
 * rail.
 *
 * It is the only control here that takes a reader's own words, and the only
 * one whose answer is the list directly under it — the four selects narrow a
 * set, this one names what you are after. Sat in the rail it read as a fifth
 * facet and pointed away from the column it changes; over the results it is
 * the first thing on the page and the count moves one line below it.
 *
 * It owns its own keystrokes and commits on a pause: the URL is the filter's
 * home, and writing it per character would refetch per letter.
 */
export function CatalogSearch({
  value,
  onCommit,
}: {
  value: string;
  onCommit: (value: string) => void;
}) {
  const [text, setText] = useState(value);
  const [synced, setSynced] = useState(value);

  // An external change (a pasted link, Clear the filter) resyncs the input
  // during render rather than in an effect, per the React docs' "adjusting
  // state when a prop changes".
  if (value !== synced) {
    setSynced(value);
    setText(value);
  }

  useEffect(() => {
    if (text === value) return;
    const timer = setTimeout(() => onCommit(text), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text, value, onCommit]);

  return (
    <div className="relative">
      <Search
        className="text-muted pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2"
        aria-hidden
      />
      <input
        type="search"
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder="Search titles and abstracts"
        aria-label="Search titles and abstracts"
        // 16px until `md`: iOS Safari zooms the page when a focused control
        // is under 16px and does not undo the zoom on blur.
        // Chromium draws its own clear glyph inside a `type=search`, which
        // would sit beside ours as a second X meaning the same thing.
        className="border-line bg-panel text-ink placeholder:text-muted hover:border-ink/25 focus:border-teal-ink/40 w-full rounded-md border py-2.5 pr-10 pl-10 text-[16px] transition-colors outline-none [&::-webkit-search-cancel-button]:appearance-none md:text-[14px] motion-reduce:transition-none"
      />
      {text !== "" && (
        <button
          type="button"
          onClick={() => setText("")}
          aria-label="Clear search"
          className="text-muted hover:text-ink absolute top-1/2 right-2.5 -translate-y-1/2 rounded p-1.5 transition-colors motion-reduce:transition-none"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      )}
    </div>
  );
}
