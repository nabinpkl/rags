/** arXiv id-months (`YYMM`) rendered as human dates.
 *
 * An id-month is already the authority for when a paper entered the corpus,
 * so this splits strings and never parses a date — the API derives the window
 * from the ids themselves, and a formatter that re-parsed them could disagree
 * with the corpus it describes.
 *
 * It lives here because two surfaces render the same window (the hero's
 * sentence and the rail's chip) and a second copy would drift the first time
 * one of them was corrected.
 */
export function formatIdMonth(yymm: string, style: "long" | "short" = "long"): string {
  const year = 2000 + Number(yymm.slice(0, 2));
  const name = new Date(Date.UTC(year, Number(yymm.slice(2)) - 1, 1)).toLocaleString("en-US", {
    month: style,
    timeZone: "UTC",
  });
  return `${name} ${year}`;
}

/** "Jul 2026 – Aug 2026" for a chip, collapsed to one month when the window
 * is one month. Null when the graph is empty: the caller renders nothing
 * rather than a range with a missing end. */
export function formatIdMonthRange(start: string | null, end: string | null): string | null {
  if (!start || !end) return null;
  if (start === end) return formatIdMonth(end, "short");
  return `${formatIdMonth(start, "short")} – ${formatIdMonth(end, "short")}`;
}
