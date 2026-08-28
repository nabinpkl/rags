# Agentic trends over raw cs.CL — no index, no RAG

Status: **in progress**, 2026-08-23. Owner directive: "first download whole
cs.CL, then agentic trend over it, without indexing or RAG." This replaces
the deterministic-first ordering in `2026-08-23-trend-index.md`; that
plan's transparency rule (§1 there) still governs what the agent may claim.

## 0. Where things stand

- **Download running**: all cs.CL-primary PDFs (83,362 ids from the Kaggle
  seed, 2007 → 2026-06-27) from the Google mirror onto `/mnt/data/askrag/
  corpus/pdfs/`, 8 connections, version-pinned. Log: `/mnt/data/askrag/
  logs/cscl-backfill-20260823.log`. ~5.5 papers/s → ~4–5 h. ~1–2 % of
  ids miss on the mirror and fall back to the paced scraper; a few 404
  (withdrawn). The collector's `arxiv.db` gains a metadata row per paper
  as it goes — after this run it *is* the cs.CL catalog (title, abstract,
  authors, categories, published, version) without any further step.
- Bug fixed on the way: `run()` recorded `pdf_path` relative to
  `collector/` instead of `corpus/` (crashed on the first batch; the other
  recipes were already corpus-relative). Four sites changed to
  `CORPUS_DIR`; 20 collector tests pass. Uncommitted.
- Gap to close after the run: July–August 2026 cs.CL (~3k papers) are not
  in the seed; `update --category-prefix cs.CL` via OAI or a newer seed.

## 1. What "no index, no RAG" means here

The agent works the way a coding agent works a repository: **grep, count,
open, read** — over plain files and one SQLite table. Nothing is chunked,
embedded or ranked. The only preprocessing is turning each PDF into a
plain-text file once, because `rg` needs text, not PDF:

| | measured | whole cs.CL |
|---|---|---|
| PyMuPDF plain `get_text()` | 0.12 s/paper, 64 KB/paper | ~45 min on 4 cores, ~5.3 GB of `.txt` |
| `rg` over 5 GB of text | seconds | — |
| `arxiv.db` metadata queries | ms | 83k rows |

`corpus/text/<yymm>/<id>.txt` is a cache of the PDF's own bytes, page
breaks kept (`\f`) so a hit can still say "page N". It is not served, not
mounted into anything (§6b applies to it exactly as to `pdfs/`), and can
be deleted and regenerated at will. This is the line between "a text
cache" and "an index": the cache has no structure the agent reasons
about; it is the paper, flattened.

## 2. The agent

A **batch analyst**, not the chat agent: one run = one question over one
window (a month, a quarter, a year), producing a structured report. Same
hand-built loop (D2), same model policy (D3: Haiku for the loop; a strong
model only for a final judge pass if we add one), same tool discipline
(§5: read-only, enum'd ops, fenced paper text), **different budget**: an
operator budget per run set in `config.py`, outside D11's visitor caps.

Tools (literal registry entry each, `askrag/tools/`):

| tool | contract | what it is underneath |
|---|---|---|
| `count_catalog` | `{terms: [..], field: title\|abstract\|both, match: any\|all, primary_only: bool, from: YYYY-MM, to: YYYY-MM, group: month\|quarter\|year}` → `[{period, n, denominator}]` + up to 20 sample ids per period | `LIKE`/FTS over `arxiv.db` (metadata, CC0) |
| `grep_fulltext` | `{pattern (literal or safe regex), from, to, max_papers ≤ 200, context ≤ 2 lines}` → `[{arxiv_id, page, line}]` | `rg --json` over `corpus/text/<yymm>/` restricted to the window; regex validated (no backrefs, bounded length), time-boxed |
| `list_papers` | `{from, to, primary_only, cursor}` → ids + titles + first 300 chars of abstract | `arxiv.db` |
| `read_paper` | existing tool, pointed at `corpus/text/` (page-bounded, token-capped) | the text cache |
| `sample_papers` | `{from, to, n ≤ 30, seed}` → deterministic random sample | `arxiv.db` |

No `search_corpus`, no vector store, no `drive_ui`. `query_metadata`'s
enum discipline carries over verbatim: the model never writes SQL or an
unbounded regex.

### The loop's job, and its output contract

Prompted as an analyst, not a writer: *propose a trend → turn it into a
countable rule → count it over the window and a baseline window → sample
papers that match → read enough of them to confirm the rule means what
the label says → report.* A trend without a rule and counts is rejected
by the schema; a rule whose samples the model could not confirm is
reported as "unconfirmed" rather than dropped silently.

Report schema (one JSON per run, `reports/<scope>/<window>.json`):

```
{ scope: "cs.CL", window: "2026-06", baseline: "2025-12..2026-05",
  catalog_stamp: {seed: "2026-06-27", oai: null, n_papers: 1601},
  model: "...", cost_usd: 0.0, tool_calls: 0,
  trends: [{
    label: "state-space models in long-context LMs",
    rules: [{tool: "count_catalog", args: {...}}, {tool: "grep_fulltext", args: {...}}],
    counts: [{period, n, denominator}],      # verbatim tool output, re-runnable
    direction: "rising|falling|flat|new",
    evidence: [{arxiv_id, page, quote ≤ 50 words, why}],  # ≥ 3, §6c caps
    confidence: "confirmed|partial|unconfirmed",
    caveats: ["rule also matches X", ...]
  }],
  not_found: ["things the model looked for and did not find"]  }
```

Every field the site renders comes from a tool result, not from prose;
the prose (`label`, `why`, `caveats`) is labeled AI-generated and sits
next to the rule that anyone can re-run and flag (trend-index plan §1).

### Run modes

- `just trend window=2026-06` — one window, one report.
- `just trend-backfill from=2016-01 to=2026-06 step=quarter` — the
  historical series, sequential, resumable by window (a report file
  present = skip).
- Reports are committed? No — they are build artifacts under `corpus/
  reports/` and the site reads them; the *rules* the agent proposed are
  the durable output and get appended to `trends/vocabulary.py` as
  `origin: agent` for human review.

### Cost (to be measured on the first run; estimates)

A run is ~30–60 tool calls, mostly small (counts, id lists), with a few
`read_paper` calls at ≤ 16k tokens each. Haiku 4.5 at the D3 table: ~\$0.3–
1 per window. The 2016→2026 quarterly backfill (42 windows) ≈ \$15–40 once;
monthly thereafter is cents. A strong-model judge pass (the evals pattern
from D14) would multiply that by ~5–10 and is not assumed.

## 3. Sequence

1. **Now**: backfill finishes → `just status` shows ~83k rows; spot-check
   5 random PDFs open; July–Aug top-up via OAI.
2. `text-cache` recipe: PyMuPDF plain text → `corpus/text/`, 4 workers,
   resumable (mtime rule from `extract_pdfs.py`), skiplist for the
   unparseable tail. ~45 min.
3. The five tools + tests (security-relevant: regex validation and
   time-boxing for `grep_fulltext`, enum'd args everywhere, text fencing in
   `read_paper` output — all test-first per §6).
4. `askrag/trend_agent/` (loop runner reusing `agent/loop.py`, the
   analyst prompt, the report schema and validator, the `just trend`
   recipes). First real run on `2026-06` with the cost badge on;
   measured numbers go in the decision record.
5. Render: the `/trends` page from the trend-index plan reads the reports
   — counts as charts, evidence as paper rows, rule as the permalink, flag
   button — unchanged in shape, now fed by the agent's rules instead of
   a hand-curated list.
6. Decisions to record (spec): D17 "cs.CL full-text store + plain-text
   cache, never served"; D18 "batch analyst agent: operator-budgeted,
   report schema is the contract"; D12 amendment for the monthly cs.CL
   delta (metadata + PDFs only — no embeddings needed on this path, so the
   9 h/month CPU wall from the freshness plan disappears).

## 4. What this does not do (on purpose)

- No vector search, no chunks, no Chroma for cs.CL. The existing 6,460-
  paper RAG corpus is untouched and still what the chat agent serves;
  merging the two is a later decision (D16 territory).
- No popularity signals, no LLM narrative without a rule behind it, no
  institution claims — the trend-index plan's rules stand.
- Nothing from `corpus/text/` or `corpus/pdfs/` is ever mounted into a
  serving container.
