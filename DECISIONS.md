# Decisions log

Decisions made outside (or after) the design spec. Newest first. Every entry
that changes architecture must name the spec section updated in the same PR;
"Spec updated: no" is only valid for process-only decisions.

Format:

```
## YYYY-MM-DD — <one-line decision>
Context / Decision / Alternatives rejected / Consequence
Spec updated: <section or "no (process-only)">
```

---

## 2026-09-18 — embeddings move to pplx-embed-v1-0.6b over OpenRouter (D5 third amendment)

**Context.** The corpus held 40,116 chunks but only 33,931 vectors: 144
papers had none at all, including RoBERTa (1907.11692), MMLU (2009.03300),
GCG (2307.15043) and AutoGen (2308.08155) — the foundations the landing page
names. They answered to BM25 alone, silently. Closing that gap locally is
2.6 CPU hours at the measured 0.66 chunks/s, and the whole corpus is 16.9,
which is why the indexed set was curated small in the first place.

**Decision.** `embedding_backend` gains `"openrouter"` and becomes the
default, model `perplexity/pplx-embed-v1-0.6b` at 512 dims. Measured on the
same 33,931-chunk pool with identical queries and cosine in both spaces, one
mid-chunk 30-word span per paper retrieving its own chunk out of 33,931
candidates (n=667):

| | nomic-512 | pplx-512 |
|---|---|---|
| recall@1 | 0.457 | 0.562 |
| recall@5 | 0.649 | 0.781 |
| recall@10 | 0.718 | 0.837 |
| MRR@10 | 0.539 | 0.656 |

Ten to thirteen points on every metric, past D14's 5-point noise floor, and
the two spaces' top-10s overlap only 3.5/10 on that task, so they are not
two views of one ranking. A title-to-own-paper task saturates for both
(recall@1 0.996 vs 0.999) and gates nothing; it is recorded only to show
neither space is broken. The full corpus embedded in 679s for $0.0849.

**Alternatives rejected.** *Stay local and run the 2.6-hour top-up* — buys
coverage but not the 11 points, and leaves every future re-embed at 17
hours. *Fireworks' hosted nomic at $0.008/Mtok* — keeps the model, so the
existing vectors stay valid, but a different serving stack (pooling, dtype,
weights version) can shift vectors in ways that show up as worse recall
rather than an error, and mixing stacks in one collection is unmeasurable.
*voyage-4-lite, the path D5's second amendment parked* — same $0.02/Mtok as
OpenAI's small model, five times pplx's price, and no measurement favouring
it. *Wait for #18's golden set* — the harness does not exist and #17's
verification pass is human work; the coverage hole is real today.

**Consequence.** Retrieval now depends on outbound TLS at query time, at a
measured 107 ms/query against 264 ms for the local model on this box. D8's
fail-soft boundary degrades the vector leg to BM25-only on a transport
error, which was confirmed by accident when the sandbox proxy's CA broke
httpx. Perplexity rate-limits upstream of OpenRouter: five 429s in the bulk
run, every one cleared by a single 5s retry, and all five traced to a
cold-start burst of 1.1M tokens in 15 seconds. Hence
`askrag/ingest/token_bucket.py`, which reserves tokens forward in time and
banks nothing, so an idle stretch earns no credit for a later burst; a
sliding window over recent spend is what produced the burst. Batch caps are
the provider's own measured 400s: 512 items, 120,000 tokens. The vectors
computed during the experiment were imported as the pipeline's parquet
rather than re-embedded, normalized on the way in (raw norms ranged 1.55 to
11.97, and chroma's default space is l2). The nomic collection is left in
chroma, so rollback is one env var plus a restart. The span task is a proxy,
not #17's golden set: its query text appears verbatim inside the target
chunk, so it rewards lexical-semantic alignment and measures the vector leg
alone, not the hybrid the app serves.

Spec updated: D5 (third amendment)

## 2026-09-17 — the Field facet is a topic list, not a select

**Context.** The rail's four selects (see "one rail", 2026-09-16) hid what
the catalog holds behind a closed control. The owner asked for a topic list
with icons and counts.

**Decision.** Topics render as rows (`components/catalog/topic-filter.tsx`):
the nine largest, each with a lucide glyph, the arXiv name and a compact
count (glyphs from `lib/category-icon.ts`, the map the cards already use), and the rest folded under "Others (n)" with their summed count. Nine
held 89% of the unfiltered catalog. A row is a toggle; a selected topic from
the fold stays visible. The list sits last in the rail so it pushes no
select down. Glyphs are one ink colour, not a colour per topic: colour in
this app means state or a chart series. Month stays a select (234 values).
The facets query now keeps the previous counts while the next load, so a
pick no longer unmounts the rail's lists.

**Rejected.** A coloured dot per topic, as in the reference image: 40
colours with no meaning, and the accent would stop marking selection.
Shortened names ("Computer Vision"): a second, unofficial name for the same
code; arXiv's names wrap to two lines instead.

**Revisit trigger.** The fold holds a topic readers pick often, or the
catalog's cs share drops so the top nine stop covering most of it.

Spec updated: no.

## 2026-09-17 — cs category names are a hand-kept table

**Context.** The Field filter and the card chips show codes (`cs.CL`) with
no name. Neither source we ingest names a category: the Kaggle snapshot and
the GCS mirror's `metadata-v5` both carry codes only, and the whole mirror
bucket holds no taxonomy file. arXiv's API names them, but it is
export.arxiv.org (D18).

**Decision.** `backend/askrag/category_names.py` holds the 40 `cs.*` names,
copied by hand from https://arxiv.org/category_taxonomy on 2026-09-17 (one
manual read, no code path fetches it). The backend sends the name on each
category facet bucket; other archives' codes carry no name and show as
codes. `build_indexes` refuses a corpus holding a `cs.*` code the table does
not name, so a new class stops the build rather than reaching the page
unnamed.

**Rejected.** Fetching the taxonomy at build or view time (a fan-out to
arxiv.org, and a build that depends on arXiv being up). A copy in the
frontend (a second home for the same fact). Naming all 155 codes the corpus
holds: most are single cross-listed papers, and the build guard would then
fail on every new archive a cited work comes from.

**Revisit trigger.** The build fails on an unnamed `cs.*` code, or the
Overview page starts showing non-cs categories to readers.

Spec updated: no (the spec does not cover display names).

## 2026-09-16 — sturdier typefaces: Atkinson Hyperlegible Next, Source Serif 4, JetBrains Mono

**Context.** The owner found the text thin to read. Instrument Sans is a
narrow face with light strokes at 400, and it carries the catalog's abstracts
and author lines at 12-15px. STIX Two Text has hairline serifs that thin out
further at the foundations table's row size.

**Decision.** Sans: Atkinson Hyperlegible Next (built for legibility; wider
letterforms, heavier strokes at the same weight). Serif: Source Serif 4, whose
optical-size axis thickens strokes at small sizes. Mono: JetBrains Mono, with a
taller x-height for the 10-11px labels. All three are variable and still
self-hosted by next/font (§4b unchanged). Tokens (`--font-sans/serif/mono`)
keep their names, so no component changed.

**Rejected.** Raising the weight of the old faces: Instrument Sans at 500
stays narrow, and every `font-medium` would have had to step up to hold the
hierarchy. IBM Plex Sans: close second, lighter at 400.

**Revisit trigger.** The page's look is judged against `docs/mockup.html`
again, which still names the old faces; update the mock if it is regenerated.

Spec updated: no (the spec does not name typefaces).

## 2026-09-16 — one rail, addressing views rather than bands

**Context:** Two routes had grown two rails. The dashboard's listed four
scroll-spied bands of its own canvas plus, separated and captioned, one link
out; the catalog's listed five filter controls under a different tagline and
no way back except a button in the top bar. Same width, same position, two
different vocabularies, and neither said what the other view was.

**Decision:** one `components/shell/shell-sidebar.tsx` for both routes. It
addresses the two VIEWS the app has — Overview at `/`, Explore at `/papers` —
and takes a slot below the nav that the view fills; today only Explore does,
with its filter. The dashboard's band rows and the scroll-spy that lit them
(`hooks/use-active-section.ts`) are deleted, not hidden: the canvas is four
panels tall, so scrolling reaches them faster than aiming at a row does, and
the rows cost a reader the question of whether a rail row scrolls or
navigates. The two duplicate route buttons in the top bars go with them.

**Alternatives rejected:** keeping the band rows above the view rows (two
kinds of target in one column is the problem, not the ordering); a second
rail for the filter (two columns of chrome before any papers appear on a
768px viewport); collapsing the filter into a dropdown in the top bar (five
controls and 234 months is a rail, which is why it was one).

**Consequence:** the shell docks at one breakpoint now, and it is `md`, the
catalog's. The dashboard's rail used to dock at `lg`, so between 768 and
1023px the foundations table gives up 264px it used to have and wraps titles
to three or four lines. That is the price of the column not moving when the
reader switches views, and it is the direction the merge has to go: a filter
that is a drawer on a laptop is worse than a table that is narrower on one.

Spec updated: no — §4c decision 2 still describes the routes, which are
unchanged; this is shell composition inside them.

---

## 2026-09-16 — card images rendered on demand, cached as files

**Context:** `/papers` lists 65,503 rows of title, authors and two lines of
abstract. A figure is the fastest thing a reader judges a paper by, and every
PDF is already on disk.

**Decision:** `/thumbs/{arxiv_id}.jpg` — Caddy serves it off disk, and on a
miss falls through to `GET /api/thumb/{id}`, which renders a 320px crop from
the local PDF, writes it into the same tree and returns it. The cache is the
file: no manifest, no `papers.thumbnail` column, nothing on the wire. `just
thumbnails` only warms the backlog.

**Why not a build artifact.** The first two versions were: a licence-gated
batch render, then a manifest read into a `papers.thumbnail` column. Both made
a card image wait on a corpus rebuild, and the licence gate left 60% of rows
showing a grey glyph. On demand removes the coupling entirely — a new month
of papers shows pictures the moment its PDFs land.

**Why every paper.** A low-resolution crop beside a link back to the source is
the indexing use *Kelly v. Arriba Soft* (9th Cir. 2003) and *Perfect 10 v.
Amazon.com* (9th Cir. 2007) held to be fair use. The licence then governs what
the CARD says: a CC paper names and links its licence beside the attribution
it already carried, an arXiv-default paper owes only the link back. We never
host the download.

**Cost, stated:** the api container now mounts `pdfs/` read-only, where its
absence used to be the guarantee that no serving path could reach an e-print.
The guarantee moves to `routes_thumbnails.py`: one reader, a whitelisted
arXiv-id pattern before any path is built, a rendered JPEG returned and never
the source, both asserted in tests. Also: askRAG must stay non-commercial or
the 5,233 NC papers' crops come down.

**Revisit when:** askRAG stops being non-commercial, arXiv states a position
on derived images, or a rightsholder objects to a specific paper (§6b's
takedown path covers it; deleting one JPEG is the whole remedy).

Spec updated: yes — new decision D19.

---

## 2026-09-16 — a route that lists papers the app cannot retrieve

**Context:** The dashboard counts 65,503 papers and can offer 811. Every
number on it opens a list, and every list is `INDEXED_PREDICATE`-scoped
(D16), so the other 64,692 papers are visible as arithmetic and unreachable
as papers. The reader who asks "what else is in there" has nowhere to go.

**Decision:** A third static route, `/papers`, backed by
`api/routes_catalog.py`, lists and filters the whole `papers` table. Rows
carry an `indexed` boolean; an indexed row opens the reader, every other row
opens arxiv.org at the recorded version (§6b). Filtering is SQL plus BM25
over a new `papers_fts` (title + abstract) built in `_write_corpus_db` — no
embedding model, no LLM, and no dependence on having fetched a PDF, since the
Kaggle snapshot carries a title and abstract for every row.

**Alternatives rejected:** Widening `/api/papers` instead (it is the agent's
own browse surface — widening it widens what the model can reason about, which
is the bug D16 closed); a section on the dashboard rather than a route (a
filter with five controls and 65,503 rows is a destination, not a band in a
scrolling canvas, and the dashboard's rail addresses bands); `LIKE '%q%'`
instead of FTS (153ms per query against 3-7ms, and substring matching returns
"diffusionally" for "diffusion"); indexing chunk text for the whole corpus so
the existing surface could serve this (that is the breadth tier, ~56h of
embedding, and it is out of scope).

**Consequence:** `corpus.db` grows ~48MB (281 -> 329MB) for `papers_fts`, and
a rebuild is required before the route answers. The `indexed` field now
reaches the wire, which D16 refused; the amendment says why that is sound here
and confirms no agent-reachable surface widened.

Spec updated: yes — D16 amendment (2026-09-16, the catalog route), §4c layout
tree.

---

## 2026-09-16 — corpus.db may be rebuilt without the vector store

**Context:** July and August 2026 were backfilled to 99.95% and 99.99% of the
catalog (6,947 + 1,347 papers), which moved every number the landing page
prints. The page's numbers are metadata — `papers`, `citations`,
`catalog_months` — and are ready minutes after a collector run. The same
papers' embeddings are not: measured on this box, `embed_chunks` sustains
~1,000 chunks/hour, so the 5,161 chunks the new frontier added are five hours
of CPU. `build_indexes` refused to write corpus.db at all until every chunk
had a vector, so a dashboard number could not move until the embedder caught
up.

**Decision:** `build_indexes --without-vectors` (recipe: `just
index-metadata`) writes corpus.db and its FTS index and leaves the Chroma
collection untouched. The equality check between the parquet and
chunks.jsonl is skipped ONLY in that mode; the check that every embedded
chunk_id still exists in chunks.jsonl (the stale-parquet guard) is not. The
build logs how many chunks have no vector, and `BuildStats` carries the
count, because this is the one build that ships the two stores out of step on
purpose.

**Cost, stated:** papers chunked since the last full build are findable by
keyword and invisible to vector search until `just index` runs. They still
count as indexed (D16's predicate is a `chunks` row, and quotes come from
corpus.db), so nothing on the page dead-ends.

**Revisit when:** embedding stops being the slow leg — a GPU, a hosted
embedder (D5's Voyage seam), or a corpus that grows more slowly than it
embeds. Then the mode is dead weight and should be deleted rather than kept
"just in case".

Spec updated: no (build-mode only; D4's two-store invariant is unchanged for
every full build, which is the only kind the gate and the deploy run).

---

## 2026-09-15 — the page states a measured share of arXiv, never "every cs paper"

**Context:** the landing copy claimed "we pulled every cs paper arXiv posted
in November 2007 and September 2026". Three separate faults compounded into
that sentence. (1) The window was `min/max(citing id-month)`, and 261 stray
seed papers with parsed references (1.5% of the citing side) stretched it from
two months to nineteen years. (2) Nothing in the corpus knew how many cs
papers arXiv actually posted in a month, so no claim about coverage could be
checked; measured against the catalog it is 94% for July 2026, **49%** for
August and 5% for September. (3) The parse rate divided by every catalog row
(57,206) rather than by the papers that reached the parser (20,733), printing
"30%, and the other 70% did not parse" for a parser that yields 81% and for
papers that were never collected at all. The month-by-month panel had the same
shape as a picture: bars of papers-per-month with no denominator, sitting in
the activity band as the widest panel on the row, so "19 papers in October
2025" read as a fact about October rather than about our download schedule.

**Decision:** four changes, one idea. (a) `kaggle_seed.count_cs_papers_by_id_month`
censuses the catalog (cs-primary, per id-month) and `build_indexes` writes it
to a new `catalog_months` table: our numbers now travel with arXiv's own.
(b) `papers.has_text` records which papers reached the reference parser, and
the parse rate is counted over those. (c) The window becomes a **cohort**,
derived by a stated rule (`landing_cohort_min_share`: an id-month that
contributed at least 1% of parsed papers; measured 61% / 36% / 1.3% against
0.24% for the next month down, so any threshold in 0.3%-1.3% picks the same
three). (d) `GET /api/trends` becomes `GET /api/coverage`, keyed by id-month
with the catalog total per bucket, and its panel moves to the method band as
"How much of each month we hold", saying outright that bar height is our
collection and not arXiv's output. A month whose catalog total is below our
own holdings reports **unknown** rather than a share over 100%, which is what
a snapshot older than the month it is asked about deserves.

`corpus/archive.zip` was promoted to the 2026-09-12 snapshot (the old one kept
as `archive-2026-08-22.zip`) because the census is only true against a
snapshot at least as new as our holdings: the August one listed 9,513 cs
papers for 2608 where the current one lists 14,491, and had no 2609 at all.
The agent prompt gained one line for the same reason the page did: the corpus
is a sample, and its totals are ours, never coverage of a field.

**Follow-up the same day, same idea applied one step further:** a number
being true is not a reason to print it. "16,893 papers with a parsed
reference list" and "20,733 PDFs extracted" are stage counts of our pipeline,
and no reader has a use for either; the parse rate's one reader-facing
consequence is that the counts undercount, which is a percentage, so the
methods note states the percentage and the two counts behind it stay off the
page. The freed hero slot went to `readable_papers` (the D16 indexed set),
which answers "what can I ask about here" rather than "what did they
process", and `corpus_papers` left the wire entirely: 57,206 catalog rows is
a storage fact that reads as "they have 57,206 papers".

**Alternatives rejected:** keeping "every" and narrowing the window to the
months where it is true (August is 49%, so there is no such window); deleting
the month panel (the shape of the corpus is worth showing, it was the missing
denominator that made it a lie); a coverage-share threshold for the cohort
(August at 49.4% sits right on a 50% boundary, where the parsed-share rule has
four times the margin); computing coverage in the route from the seed zip at
request time (an 85-second full pass per request).

**Consequence:** `/api/trends` is gone, so the deploy needs an api image
rebuild and a corpus rebuild (new `papers.has_text` column and
`catalog_months` table), then the usual reseed. The build gained ~85 s for the
census pass. `just mirror-status` and the census now answer the same question
from two ends: what arXiv has, and what we took of it.
Spec updated: D16 amendment (2026-09-15, count-vs-claim rule).

## 2026-09-13 — home page is the dashboard: trends + latest sections, no new route

**Context:** with the Sep-03 refresh the graph is the freshest thing on the
page, but the page showed only the ranking — no growth story, no arrivals.
**Decision:** `/` gains `GET /api/trends` (monthly counts, honest totals) and
`GET /api/latest` (newest INDEXED papers, D16 list rule), rendered as two
sections under the foundations table; hand-rolled div bars, no chart
dependency. **Alternatives rejected:** a separate `/dashboard` route (a second
front door splits the product argument); recharts/visx (a new dependency for
two bar rows fails the sdlc gate's worth-it test). **Consequence:** the deploy
needs an api image rebuild (new routes), then the usual reseed.
Spec updated: D16 amendment (2026-09-13, home-as-dashboard).

## 2026-09-13 — no code path touches export.arxiv.org (D18); versions backfill from the seed

**Context:** a routine `build_indexes` rebuild failed three times in a row —
429, read-timeout, 503 — on the version-backfill stage: one batched
`export.arxiv.org/api/query` for 31 NULL-version legacy rows. Direct probes
showed instant 429s 15+ minutes apart (no `Retry-After`): the whole IP was
throttled, almost certainly fallout from the day's paced OAI harvest. A local
build must never be hostage to one throttled host for a 31-id metadata lookup.

**Decision:** ban all three live `export.arxiv.org` consumers — the OAI-PMH
harvest, the arXiv PDF scraper (including the GCS-miss fallback), and the
backfill query — stubbed as not-implemented, not deleted, so the ban is
visible at the call site. NULL-version rows backfill from the Kaggle
snapshot's `versions` array via the existing early-exit reader (seconds for
31 ids, zero network). The `update`/`oai-*` recipes die with the OAI lane;
monthly freshness is manual snapshot + GCS pull, which already covers the
landing page's monthly cadence.

**Alternatives rejected:** keep OAI for metadata only (keeps the throttle
dependency for the smallest gain); retry/backoff on the backfill (next
throttle lands mid-build again); leave NULLs unpinned (weakens D9 pinning to
save a seed pass that costs seconds).

**Consequence:** `build_indexes` is now fully offline (seed zip + local
artifacts only). The 31 legacy rows resolve from the September snapshot on
the next build; any id the snapshot itself lacks keeps the D9 unpinned-URL
fallback, unchanged.

**Spec updated:** yes — new D18, plus D9 (seed backfill), D12 (`update`
retired), §6b rule 7 (pacing moot).

---

## 2026-08-28 — float16 embedding is a Mac setting, not a default; CPU boxes must override

**Context:** the frontier embed run did under 1,024 chunks in 105 minutes at
300% CPU. The obvious suspect (a `llama` server competing for a 4-core box) was
real but minor — pausing it moved load 8.4 -> 4.5 and changed the rate barely at
all.

**Measured 2026-08-28** on the ARM VPS, box otherwise idle, 12-64 chunks of mean
~500 tokens:

| dtype | rate |
|---|---|
| float16 (`config.embed_local_dtype` default) | ~0.01 chunks/s |
| **float32** | **0.35 chunks/s, ~165 tok/s** |

`embed_encode_batch_size` 16 vs 32 vs 64 changed nothing (0.36 / 0.34 / —), so
~165 tok/s is this box's ceiling for nomic-embed-text-v1.5 and the dtype was the
entire gap.

**Decision:** keep `float16` as the default — it is correct on the ingest Mac,
where MPS runs it natively and it halves the resident set (the reason it was
chosen, DECISIONS.md 2026-07-05). Treat it as a PER-BOX setting, exactly like
`embed_device`, and set `ASKRAG_EMBED_LOCAL_DTYPE=float32` wherever embedding
runs on CPU. The config comment now says so at the definition.

**Alternatives rejected:** *flip the default to float32* (would silently
pessimise the Mac path D5 actually specifies); *auto-detect the device and pick
a dtype* (config is settings, not logic — the codebase resolves this shape with
a documented env override, and `embed_device`'s own comment sets that
precedent).

**Consequence:** the frontier embed went from days to ~12 hours. More
importantly the trap is now written down at the setting, so the next person who
runs ingest somewhere without a GPU does not spend an afternoon blaming the
hardware. Note what the number is NOT: 165 tok/s is slow for a 137M model, so
the box, not the dtype, is the remaining ceiling.

Spec updated: no (D5's local-backend amendment already frames dtype/device as
operating points, not architecture)

---

## 2026-08-27 — The landing page defines the index frontier; three layout calls recorded

**Context:** the landing page ranks what our recent cohort cites (162,792
extracted citations over 18,844 papers), but D16 scopes the app to papers with
`chunks` rows, and only 200 had them. Every foundation the page names — Qwen3,
Llama 3, PPO — had none. A page whose every link dead-ends in the agent
advertises a capability and withholds it.

**Decision:** invert the dependency. `ingest/select_frontier.py` derives the
index manifest FROM the page's claims (top 50 cited works + up to 8 newest
citers each = 285 papers), and exactly those are fetched, extracted, chunked
and embedded. Three layout calls were made without owner input, each recorded
here with its reversal cost:

| # | Call | Reversal cost |
|---|---|---|
| A1 | Landing at `/`, app shell moved unchanged to `/app` | Low — one `git mv` and the `?paper=` deep links; the deploy healthcheck hits `/api/facets` and is unaffected |
| A2 | Union: `corpus.db` carries every `arxiv.db` paper (56,391), not a curated subset | Low — `INDEXED_PREDICATE` already hides the chunk-less ones from browse, facets, and every agent tool |
| A3 | Frontier = 50 x 8 (`config.frontier_top_cited` / `frontier_citers_per_work`) | Medium — widening either number means a re-embed, roughly linear |

**Alternatives rejected:** *index everything we hold text for* (18,844 papers,
737k chunks, ~13 days of CPU embedding for coverage no card points at); *an
`is_indexed` flag with a two-tier UI* (the exact bug D16 was written to close);
*keep the citation graph in its own database* (two universes diverging again).

**Consequence:** "every link on the page is answerable" is a property of
construction, asserted in `test_select_frontier.py`, not a coverage statistic.
The frontier is recomputed when the page is regenerated, so it tracks the story
rather than accumulating. Raising `frontier_top_cited` is now the single knob
that widens what the page claims — and it is a knob with a stated embedding
cost, which is the point.

Spec updated: D16 amendment, D12 amendment, new D17 (transient PDFs), §4c
decision 2 (a second STATIC route is compatible with the no-dynamic-routes rule)

---

## 2026-08-27 — Corpus text may spell control tokens; tokenizing must not raise

**Context:** chunking the frontier died on a paper containing a literal
`<|endofprompt|>`. tiktoken refuses special-token spellings by default. The
same call shape sits in `agent/context_window.estimate_tokens`, which runs over
messages carrying TOOL RESULTS — i.e. retrieved paper text.

**Decision:** every tokenization of corpus-derived text passes
`disallowed_special=()`, so a control-token spelling is ordinary characters.
Regression tests in `test_chunk_papers.py` and `test_context_window.py`.

**Alternatives rejected:** *strip the strings before tokenizing* (mangles the
text of any paper ABOUT language models — exactly the papers we hold most of);
*catch and skip the paper* (silently drops real papers from the graph).

**Consequence:** a paper quoting a control token can no longer take down a live
turn from inside the budget estimate. This is §6's untrusted-content posture
reaching one layer further down than the fence: corpus text must never be able
to mint a control token, and must never be able to raise inside our own
accounting.

Spec updated: no (implements §6's existing untrusted-content posture)

---

## 2026-08-13 — Theming lives in CSS variables, not `dark:` variants; next-themes owns the choice (#85, owner directive)

**Context:** owner directive — light/dark/system with an icon-button menu. The
palette was light-only apart from the agent panel's deliberately fixed
machine-room dark, and #83 had just put the app somewhere people open at
night.

**Decision:** the palette moves into `:root` / `.dark` custom properties, and
`@theme inline` maps Tailwind's color names onto them. A component writes
`bg-paper` once and never learns which theme is active — so there are no
`dark:` variants to keep in sync across fifteen files, and flipping a theme is
one variable swap. Two consequences that had to be designed, not discovered:

- **`--teal-ink` splits accent TEXT from `--color-teal-deep`, the accent
  SURFACE.** The old single token was both the chip text colour and the Ask
  button's background. Themed as one, either the dark-mode chips become
  unreadable or the button loses its contrast against near-white label text.
- **The machine-room palette is NOT themed.** The agent panel and the PDF
  surround stay dark in both themes: that half of the screen is
  instrumentation, and its darkness is the design's claim about what it is.
  Dark mode makes the explorer *approach* it, never merge with it — hence
  `--paper` at `#171c20`, a step lighter than `--color-machine`'s `#10161b`.

`next-themes` owns the choice: it writes `.dark` **before first paint** via a
blocking inline script, which a static export (D13, no server) cannot do
itself — the alternative is a flash of the wrong theme on every load. "System"
is a real third state that keeps following the OS, not a default that
collapses into light or dark.

**Dependency gate (sdlc.md):** next-themes 0.4.6, MIT, ~25.8M weekly
downloads, 6.3k stars, repo active (pushed 2026-02), **0 advisories** (GitHub
advisory DB + `pnpm audit`). Caveat recorded honestly: no npm release since
0.4.6 (2025-03) though commits have landed since — acceptable for a small
feature-complete library whose whole job is one script tag and a context, and
the revisit trigger is it going unmaintained or breaking on a React major.

**Alternatives rejected:** *hand-rolled (~40 lines: a store, an inline script,
a class toggle)* — genuinely close, but the pre-paint script is the part with
the sharp edges (storage key, system-change listener, SSR mismatch) and this
is the library everyone else's edge cases have already been filed against;
*`prefers-color-scheme` only* (no way to pin a theme against the OS);
*`dark:` variants* (fifteen files to keep in sync, and every new component a
chance to forget).

**Consequence:** the control lives in the site footer — the only element that
survives the explorer↔viewer swap AND every breakpoint, so it needs no second
instance in the app bar. The static export's prerendered HTML cannot know the
stored choice, so the button renders a neutral icon until mount.

**Revisit when.** A third theme appears (the enum in theme-menu.tsx becomes a
map worth deriving), or the design grows a surface that must differ per theme
inside the machine-room half.

Spec updated: §4b stack table, §4c frontend tree.

---

## 2026-08-13 — Responsive shell: one element that docks or drawers, never two mounted copies (#83, owner directive)

**Context:** #81 put the app on the tailnet, where it gets opened from a
phone. The three-pane layout (facet rail | corpus | agent) had no narrow
story: the 216px rail took over half a 390px screen, the table's four fixed
columns (266px) left ~120px for a title, and the agent panel — the point of
the project — stacked below the fold with nothing pointing at it. The spec
never covered viewport behavior at all.

**Decision:** two thresholds, matching Tailwind's own: the facet rail docks
from `md:` (768px), the agent panel from `lg:` (1024px), and below each it
becomes a slide-over drawer reached from a narrow-viewport `AppBar`
(hamburger for filters, a labelled toggle with a live status dot for the
agent). Between them the tablet case falls out for free: rail docked, agent
still a sheet.

The load-bearing constraint is that **each panel is ONE element wrapping ONE
child instance**, positioned by CSS — not `{narrow ? <Sheet><Chat/></Sheet> :
<Column><Chat/></Column>}`. The agent panel owns the app's only SSE
subscription (`use-agent-stream.ts`) and the facet rail owns debounced filter
inputs; a conditional render mounts those twice across a rotation, opening a
second stream or dropping a half-typed year. `drawer-panel.tsx` holds that
invariant and its test asserts the child renders exactly once in both modes.

Consequences that are easy to get wrong, so they are pinned by tests:
- A closed drawer is `invisible`, not merely translated off-screen — a
  translated panel keeps its links and inputs in the tab order, so a keyboard
  user tabs into an agent composer sitting outside the viewport.
- Dialog semantics apply only while the panel IS a drawer. Docked, it is a
  region; announcing a modal dialog would tell a screen-reader user the rest
  of the app is inert when it is not. CSS cannot answer "am I docked", so
  `use-media-query.ts` answers it in JS and `lib/breakpoints.ts` keeps the
  numbers next to the classes they mirror.

**Alternatives rejected:** *a CSS-only solution* (no way to switch ARIA roles,
and a closed drawer would keep its tab stops); *a bottom tab bar* (a third
navigation model on top of the explorer↔viewer swap and the `?paper=` URL);
*a separate mobile route* (D13's static export has one shell by design, §4c
decision 2); *a component library's Sheet* (a dependency for what is ~90 lines,
and every one I looked at re-parents its child on breakpoint change).

**Consequence:** the explorer table renders stacked cards below `md:` (same
row element, same `row.original`, no second data path) and moves sorting into
its own control, since the column headers that carried it are gone. The
viewer's cited-excerpts pane becomes a bottom disclosure so the PDF keeps the
screen. `h-dvh` replaces `h-screen` (mobile `100vh` is the URL-bar-retracted
height, which pushed the footer under browser chrome), inputs are 16px below
their breakpoints (smaller text makes iOS Safari zoom on focus and never zoom
back), and the composer pads by `env(safe-area-inset-bottom)`.

**Revisit when.** A third docked panel appears (the two-threshold scheme stops
being obvious), or a real phone shows the 45vh excerpt cap is the wrong split.

Spec updated: §4c frontend tree (shell/, ui-shell-store, use-media-query,
breakpoints).

---

## 2026-08-11 — Turn cost comes from the provider when the provider reports it (#81, owner directive)

**Context:** the tailnet deployment routes the agent through OpenRouter's cheap
smoke model, but the ledger prices every turn from `config.py`'s
`agent_usd_per_mtok_*` — Haiku's rates (D3). Measured on the deployed box: a
turn billed $0.0039 was logged as $0.0621, ~16x over. Three verification
questions "spent" the $0.10 daily IP cap (D11) while real spend was under a
cent, so the demo locked itself out. The owner asked whether pricing could come
from OpenRouter instead of being hardcoded.

**Decision:** it can come from something better than OpenRouter's price table —
OpenRouter returns `usage.cost`, the exact amount it billed, on every response,
and the Anthropic SDK preserves it as a pydantic extra (verified against the
live endpoint: `usage.cost = 2.1e-05`). New `askrag/agent/pricing.py` owns turn
accounting: `TurnCost` accumulates tokens per billing tier and prefers the
provider's figure, falling back to the config table when no cost is reported —
which is exactly the prod path, since real Anthropic sends no such field. No
config flag selects between them; the provider's own answer decides.

Two rules the tests pin, both about the direction of error:
- **A mixed turn prices from the table**, never a partial provider sum — summing
  only the calls that reported would under-report, and under-reporting is the
  one direction D11's caps cannot absorb (spend passes a gate that should have
  stopped it).
- **A non-finite, negative, bool, or non-numeric cost counts as unreported.**
  NaN especially: `nan > cap` is False, so a poisoned turn would never trip a
  limit.

**Alternatives rejected:** *fetching `/api/v1/models` pricing at startup* (a
network dependency in the budget path, a cache to invalidate, and still a
recomputation rather than the billed truth — the response already carries the
answer); *per-generation lookups via OpenRouter's generation endpoint* (an
extra request per turn for a number already in hand); *env-configured rates per
deployment* (works, but every model change becomes a two-place edit that
silently rots); *raising the caps* (treats the symptom and leaves the ledger
lying).

**Consequence:** cost badge, traces.db and the D11 cascade all now reflect real
money on the OpenRouter path; the Haiku path is byte-identical to before.
`config.py`'s rate table stays as prod pricing and fallback. Note the caps are
now meaningful for the staging box: at ~$0.004/turn, $0.10/IP/day is ~25
questions rather than two.

**Revisit when.** A provider reports cost in a different field or unit (the
extraction is one `getattr`, deliberately), or prompt-cache write pricing stops
being a sub-cent approximation on the fallback path.

Spec updated: §7 cost model (amendment 2026-08-11).

---

## 2026-08-11 — Tailnet-first deployment: same compose, loopback ingress fronted by tailscaled (#81, owner directive)

**Context:** owner directive — containerize backend + frontend and make the
stack reachable over the tailnet. #37 (public VPS, Cloudflare, backups, admin)
stays open and unblocked-by-this; what was missing is any deployable artifact at
all. The box already runs `tailscaled` with five other services published via
`tailscale serve`.

**Decision:** build the `deploy/` artifacts D13 always called for (compose,
Caddyfile, `.env.example`, plus a Dockerfile per service), and make **ingress
mode** the only thing that differs between tailnet and public. Caddy publishes
on `127.0.0.1:${ASKRAG_INGRESS_PORT}` and nothing else; `just deploy-tailnet`
runs `tailscale serve` on the host, which terminates tailnet TLS and proxies to
that loopback port. No auth layer, no public DNS, no Cloudflare — the tailnet
*is* the access control, which is exactly why it is the right first target for a
budget-capped anonymous-by-design agent endpoint.

**Alternatives rejected:** *Tailscale sidecar container* (its own tailnet node
and MagicDNS name, and `docker compose up` would be the entire deploy — but it
needs a minted auth key + state volume, and this box's convention is already
host-level `serve`; revisit if the stack moves to a host without tailscaled);
*bind Caddy straight to the tailnet IP* (simplest, but plain HTTP and no
MagicDNS cert); *public deploy now* (that is #37, and it wants the compliance +
self-attack checklist in #38 done first).

**Consequence:** the deployment is host-coupled — one step (`tailscale serve`)
lives outside compose, and it needs the tailscale operator or sudo. `just
deploy-tailnet` / `deploy-tailnet-off` wrap it; the runbook is `deploy/README.md`.
Ingress mode is the single diff #37 has to change.

Spec updated: D13 amendment 2026-08-11 + §4c `deploy/` tree.

---

## 2026-08-11 — Chroma gets a container-private copy; the corpus snapshot stays read-only (#81)

**Context:** D4/D12 say serving runs off a read-only snapshot, and #37's plan
says "corpus artifacts ro". corpus.db honours that by construction
(`db.connect_corpus()` opens `mode=ro`). Chroma does not: `PersistentClient`
writes to its own SQLite the moment it opens, so a `:ro` mount fails at startup
with `error returned from database: (code: 8) attempt to write a readonly
database` (measured 2026-08-11 against a chmod'd copy, before writing any
compose).

**Decision:** mount `corpus.db` and `models/` read-only as planned, and give
Chroma a **container-private copy in a named volume**, seeded once from the host
snapshot by a one-shot `chroma-seed` service that `api` waits on
(`service_completed_successfully`). The host snapshot is never opened writable
by anything. `just deploy-reseed` rebuilds the volume after a re-ingest.

**Alternatives rejected:** *mount `corpus/chroma` rw* (one bug away from the
container mutating the snapshot — exactly the posture D4 exists to prevent);
*bake the index into the image* (rebuild per corpus refresh, and D12 deliberately
keeps the snapshot as data, not build input); *tmpfs* (not shareable between the
seed and api containers, and re-copied on every restart).

**Consequence:** ~37 MB of duplication at the 200-paper sample. At the full
6,460-paper corpus (#15) this is the seed step's real cost and the volume's
real size — measure it there; if the copy becomes slow enough to notice at
deploy time, that is the revisit trigger for a read-only Chroma alternative or
a rebuilt-in-place index.

Spec updated: D13 amendment 2026-08-11.

---

## 2026-08-11 — torch resolves from the CPU index on linux (#81)

**Context:** the shared lock's linux torch is the PyPI build, which depends on
`cuda-toolkit` + ~20 `nvidia-*` wheels: 2.9 GB of CUDA in a venv of 5.3 GB. The
deploy target (D13: 2 vCPU / 4 GB, and the current aarch64 box) has no GPU and
never will; embedding runs are CPU/MPS by measurement (D5). A naive API image
came to ~5.5 GB on a box with 28 GB free.

**Decision:** `backend/pyproject.toml` pins an explicit `pytorch-cpu` index and
sources torch from it **for linux only**
(`marker = "sys_platform == 'linux'"`). `uv.lock` drops the whole CUDA stack;
the API image is 2.53 GB. macOS resolves exactly as before — those wheels carry
no CUDA and MPS lives in the PyPI build — so the Mac ingest path (D5's measured
operating point) is untouched.

**Alternatives rejected:** `[tool.uv] torch-backend = "cpu"` (verified inert
under `--frozen`: it does not affect a locked resolution); `uv sync
--no-install-package` for each CUDA wheel (would need all ~20 named in the
Dockerfile, and torch would import against missing libs); accepting the 5.5 GB
image (disk is the scarce resource on the target box).

**Consequence:** linux dev boxes now get CPU torch too — correct here (no GPU),
but a GPU linux machine joining the project would need this marker revisited.
`just check` stays green on the CPU wheels (backend 342 passed / 1 skipped;
frontend 110). Local venv 5.3 GB → 1.5 GB.

Spec updated: D13 amendment 2026-08-11.

---

## 2026-07-09 — Evals live at repo root; a uv-workspace prefactor is the one prerequisite (#79, owner directive)

**Context:** refining the #17 plan, the owner directed that the eval harness
live in a **root `evals/` folder**, not nested in the backend package, and asked
for a prefactor covering the prerequisites that make the eval work easier ("single
workspace uv and other"). Audited what the harness actually needs: the read seams
already exist and are clean — `db.connect_corpus()` (read-only), `HybridSearch(settings)`
(builds its own embedder + vector store), the `traces.py` reader. The only
structural gap is dependency isolation: a root `evals/` package importing `askrag`
would otherwise need a second venv duplicating the heavy ML deps (torch 2.12.1,
chromadb 1.5.9).

**Decision:**
1. **Placement:** the eval harness is a root `evals/` package (sibling to
   `backend`/`collector`), importing `askrag` and never the reverse — evals are a
   research harness *over* the app, not part of the deployed backend. Supersedes
   the spec's `askrag/evals/…` layout hint (D14 amendment updated).
2. **uv workspace (#79):** convert the repo to a uv workspace (`backend` + `evals`,
   `collector` if its deps resolve) with one shared `uv.lock`, so `evals` depends
   on `askrag` with no duplicated venv. This is a standalone **prefactor** — it
   touches `backend/pyproject.toml` + build/CI and must keep `just backend-check`/
   `just check` green on its own, separate from any eval logic. #17/#18/#78 are
   blocked on it.
3. **Config knobs** the eval issues need (`draft_model`, `judge_model`) land in the
   prefactor so eval PRs don't each churn `config.py`.

**Alternatives rejected:** *nesting evals under `backend/askrag/evals/`* (owner
directive against it; also wrong import direction — the app would carry eval code);
*a standalone `evals/` package with its own lock* (duplicates torch/chromadb into a
second venv — the exact cost the workspace removes); *folding the workspace change
into #17* (a structural build change riding a content PR; must land + stay green on
its own first).

**Consequence:** new prefactor issue #79 (Ready); #17/#18/#78 gain it as a blocker;
the D14 amendment's golden-set path is now `evals/golden.jsonl`.

**Spec updated:** D14 (Amendment 2026-07-09 — path + workspace note).

## 2026-07-09 — Eval harness reshaped for an agentic loop: three layers, dataset-as-code, no online eval (#17)

**Context:** planning #17 (the golden set), the owner pushed on the issue's
"the YAML is the deliverable" framing ("not blind things like yml... online
offline we might not need online"). Surveyed July-2026 field practice for RAG +
agent evaluation to shape #17 to our usecase rather than copy a generic config.
Findings that changed the design: (a) agentic systems need a *trajectory* layer
(grade the tool-call sequence, not just the final answer) on top of the
retrieval + generation split; (b) golden sets are dataset-as-code (in VCS,
diff-able, code-reviewed) — a frozen launch set is "a benchmark, not a
regression suite"; (c) citation accuracy (precision/recall) is its own metric,
distinct from faithfulness, and faithfulness ≠ correctness; (d) LLM-judge must
be a different model family from the generator and calibrated against a human
slice; (e) online eval = live per-request scoring of production traffic.

**Decision:** amend D14 (see spec) — keep everything it got right (in-repo,
hand-verified, gates D7/D8/#18/#19, reuses `traces.db`) and add:
1. **Dataset-as-code:** `evals/golden.jsonl` in a root `evals/` uv-workspace
   package (JSONL supersedes the `golden_set.yaml` framing — line-diffable,
   append-friendly), versioned and code-reviewed; not frozen (cases retire,
   labels corrected). Placement + workspace set by the 2026-07-09 refinement
   below (#79).
2. **Layer 3 — trajectory** from `traces.db`: tool-call correctness, step
   efficiency vs `max_tool_steps_per_message`, loop/waste, stop-reason, latency
   + cost. Data already captured; this is the differentiated agentic layer.
3. **Citation accuracy** (precision + recall) + **answer-correctness vs
   `expected_*`** as explicit layer-2 metrics, alongside faithfulness (§6c).
4. **No online eval:** a live scorer costs money against ≤$22/mo with no traffic
   to score; instead the offline harness replays a *sample of real `traces.db`
   turns* on demand — the production-shaped insight without a standing service.
5. **Judge hygiene:** judge is a stronger/different family than the Haiku agent;
   a one-time human-vs-judge agreement slice is reported so numbers are citeable.

**Alternatives rejected:** *bare `golden_set.yaml` as the deliverable* (blind —
no harness, no trajectory layer, YAML diffs poorly for eval records); *two
layers only* (retrieval + answer — misses the agent loop, which is our thesis);
*live online-eval service + drift crons + judge registry* (enterprise-scale
machinery our traffic and budget don't warrant); *faithfulness as the sole
generation metric* (a grounded answer can still be wrong).

**Consequence:** #17's acceptance grows the trajectory + citation items; format
moves YAML→JSONL. #17 stays blocked by #14 (needs the embedding run to have
chunks to retrieve/sample) — design now, build after #14.

**Spec updated:** D14 (Amendment 2026-07-09, #17).

**Context:** the explorer advertised "Search 6,460 papers" but `corpus.db`
was built from a diverse ~200-paper SAMPLE (the full ingest is #15, still
pending). Browse returned all 6,460 `papers` rows while search/read/
excerpts only ever cover the ~200 with `chunks` rows — two universes
diverging silently, surfaced in the M4 live demo (2026-07-09).

**Decision:** the corpus the app serves = the INDEXED corpus. A single
predicate, `askrag.facets.INDEXED_PREDICATE` (`EXISTS (SELECT 1 FROM
chunks c WHERE c.paper_id = papers.arxiv_id)`), is now unconditionally part
of `facets.where_clause`'s WHERE — not a `CountFilters` field, since it has
no "off" state a caller can request. Every consumer of `where_clause`
(browse's `total`/rows, `GET /api/facets`, `query_metadata`'s
`count_papers`) inherits it automatically; `GET /api/papers/{id}` 404s a
chunk-less paper via its own `n_chunks` check. The frontend never sees a
non-indexed paper, so there is no `is_indexed` flag, no two-tier UI, no
badges — "showing N of {total}" and the facet totals already read the API
total and auto-scope, no frontend change beyond dropping the hardcoded
"Search 6,460 papers" placeholder (now generic).

**Deviation from the issue's suggested layout:** the issue named
`api/explorer_queries.py` as the predicate's home. That file doesn't exist
and isn't in the spec's §4c tree — the browse query already lives in
`routes_explorer.py` and already builds its WHERE via
`facets.where_clause`/`CountFilters` (shared with `GET /api/facets` and
`query_metadata`, D-2/#27). Adding a new file for one constant would create
a near-duplicate concept next to the module that already owns query
predicates; the constant lives in `askrag/facets.py` instead, imported by
`routes_explorer.py`. Revisit only if `facets.py` grows unrelated
responsibilities and needs splitting.

**Consequence (in scope):** `query_metadata`'s `count_papers` op — an agent
tool, not just the explorer UI — also becomes indexed-scoped, since it
shares `count_scalar`/`count_grouped` with `GET /api/facets` (D-2/#27, no
second copy of the query). This is intentional: the agent can only actually
retrieve indexed papers via `search_corpus`/`read_paper`, so a full-corpus
count would mislead it the same way the frontend was misled.

**Revised during review (2026-07-09, reviewer round 1 + coordinator
arbitration on PR #74):** the first version of this decision left
`corpus_stats` (`_run_corpus_stats`) unscoped as a "fast-follow," reasoning
it was outside #73's literal acceptance checklist. The reviewer flagged
that as underselling the defect: `corpus_stats.n_papers` reporting the full
~6,460 `papers` table is a live re-manifestation of the exact bug #73
exists to kill, just moved from the frontend header into the agent's
mouth — a user asking "how big is your corpus?" gets "6,460 papers" from
`corpus_stats` while `count_papers`' category buckets sum to ~200, an
in-conversation contradiction reachable in a single turn. The coordinator
arbitrated for the reviewer's Option B over deferring: `_run_corpus_stats`
now applies `INDEXED_PREDICATE` directly to its own `n_papers`/`year_min`/
`year_max`/`n_categories` query (rejecting Option C, which would have
un-shared `count_papers` from the predicate to "fix" the mismatch by
regressing the other direction instead). `query_metadata`'s `paper_facets`
needs no change: it reports a specific, caller-known paper id's real
`n_chunks` (0 for an unindexed one), which is honest by construction, not a
total that can diverge. D16's "risks accepted" section below reflects this
final, uniformly-scoped state, not the original interim version.

**Round 2 (2026-07-09, same PR #74): the system prompt itself hardcoded the
same number.** Flagged alongside the round-1 fix as a related-but-unfixed
finding: `askrag/agent/prompts.py`'s `SYSTEM_PROMPT` told the model *"a
corpus of 6,460 arXiv computer-science papers"* unconditionally, on every
turn — the same bug class as the frontend placeholder and the pre-fix
`corpus_stats`, but worse: it needs no tool call to surface, so fixing
`corpus_stats` alone left the model able to quote "6,460" straight from its
own instructions regardless of what the tool returned. The coordinator
rejected opening a fast-follow for this one (unlike `corpus_stats` in
round 1) and folded it into this PR instead: `SYSTEM_PROMPT` now says
"a corpus of arXiv computer-science papers" (no number) plus an explicit
instruction to call `corpus_stats` for the real count/year/category range
rather than assume or remember one, since the corpus is still growing
(#15). No test file existed for `prompts.py` (a static string, not logic)
so none was added, matching how the frontend placeholder change was
handled.

**Alternatives rejected:** an `is_indexed` flag with a two-tier UI (the
issue explicitly rules this out — the frontend should never reason about a
paper it can't retrieve); filtering only at the FastAPI route layer instead
of the shared SQL predicate (would require three separate WHERE edits
instead of one, reopening exactly the copy-paste risk D-2/#27 closed);
leaving `corpus_stats` unscoped as a fast-follow (superseded above — it
kept the M4-demo bug reachable through agent answers, not just the
frontend, until the fast-follow landed); opening a fast-follow for the
system-prompt fix too (rejected in round 2 — the fix was three lines,
deferring it would have shipped a still-live copy of the exact bug this
whole decision exists to close).

**Revisit trigger:** #15's full ingest running, at which point the
predicate matches ~all 6,460 papers and every total (`total`,
`count_papers`, `corpus_stats.n_papers`) reads accordingly — no code change
needed, this was designed to self-resolve. The system prompt needs no
revisit: it never names a number to begin with.

**Spec updated:** yes — new D16 (see spec's decision-record list).

---

## 2026-07-09 — drive_ui wiring (#32): confirmed-only ui_action queue (D-1), a store-decoupled bridge hook (D-2), one-tick goto_page + verified sequencing (D-3)

**Context:** #32's task brief handed down three coordinator decisions to
build against (not open questions): D-1 apply on confirmed only, D-2 a
bridge-hook seam between `agent-session-store.ts` and `viewer-store.ts`, D-3
the multi-tick sequencing (goto_page one-tick + `use-viewer-url-sync.ts`
survives rapid agent-driven pushes). The brief also named a concrete gap to
close: `pendingCall` was built only `if paperId`, so `set_filters` (which
carries no `paper_id`) was silently dropped from reconciliation.

**D-1 — Apply on CONFIRMED, never provisional.** `agent-session-store.ts`'s
`PendingCall` now carries the full `UiActionEvent` (not just extracted
`paperIds`), captured for EVERY `ui_action` regardless of whether it has a
`paper_id` — closing the `set_filters` gap. A new `confirmedUiActions` queue
fills only when the paired `tool_result_summary` is `ok=true` for the same
pending call's `resultName` — the exact same reconciliation branch that
already fed `verifiedPaperIds` (DECISIONS.md 2026-07-08), extended to also
push the full action. An `ok=false` result (drive_ui.py's own corpus.db
check rejected the target) reaches neither `verifiedPaperIds` nor
`confirmedUiActions` — a hallucinated target never navigates.

**D-2 — Bridge is a hook; stores stay decoupled.** New
`hooks/use-drive-ui.ts` mirrors `use-viewer-url-sync.ts`'s role: it
subscribes to `agent-session-store`'s `confirmedUiActions` (by array
reference, so the effect only fires on a genuine new confirmation) and calls
a new `viewer-store.applyDriveAction(action, args)` for each queued action,
then drains the queue via a new `drainConfirmedUiActions()` store action
(atomically empties and returns it). `agent-session-store.ts` itself imports
nothing from `viewer-store.ts` — it only ever produces the queue. Mounted
once in `AppRegion` (`app/page.tsx`), alongside `useViewerUrlSync()`, for the
same never-unmounts reason #29's entry already gives for that hook.

**D-3 — One-tick goto_page + sequencing survives.** `viewer-store.ts`'s
`applyDriveAction` sets `paper`+`page` in a single `set()` call for
`goto_page` (one store update, one tick), maps `year_min`/`year_max` onto
`yearFrom`/`yearTo` for `set_filters`, and clears `paper`/`page` on
`set_filters` — the routing rule the brief named explicitly
(`open_paper`/`goto_page` → viewer, `set_filters` → back to the explorer,
since `AppRegion` keys the swap on `paper`). Tracing through
`use-viewer-url-sync.ts`'s existing classifier (the round-1 fix, DECISIONS.md
2026-07-09 below) showed it already satisfies the "rapid sequential pushes"
requirement as written: it classifies by comparing the current store-derived
string against `prevStoreString` (what the store said last time the effect
ran), never against whether the live URL has caught up to an earlier push —
so a second store-driven change lands correctly even while the first push
is still uncommitted. No code change was needed in that file; this PR adds
`tests/use-viewer-url-sync.test.ts` (new — closing a pre-existing gap, since
neither #28 nor #29 added a direct unit test for this hook) proving it
against a mocked router that deliberately defers committing a push, plus the
back/forward + shared-URL round trip (acceptance item 2).

**Alternatives rejected:** having `use-drive-ui.ts` apply directly off the
raw/provisional `ui_action` event and roll back on a later `ok=false`
result — the frontend rules' "verify before act" posture (DECISIONS.md
2026-07-08) already rejected this shape for `verifiedPaperIds`, and applying-
then-reverting a navigation is a worse user experience than not navigating
until confirmed; keeping `pendingCall` as a single slot rather than a stack —
the loop dispatches one tool call, awaits its result, then continues (traced
through `agent-session-store.ts`'s existing `idx = findIndex(e => e.result
=== null)` invariant: at most one timeline entry lacks a result at a time),
so a single slot is sufficient and a stack would be unused complexity.

**Consequence:** `pnpm test` (106/106, up from 79), `pnpm lint`, `pnpm
typecheck`, `pnpm format:check` (this PR's files only — `openapi.json`'s
pre-existing formatting drift predates this PR, untouched) all clean.
`pnpm build` (real Turbopack production build, worktree node_modules
symlink replaced with a local install for this worktree only, per #29's
precedent) succeeds. Live-verified against the real corpus (`0704.0217`)
and a locally run `just serve`-equivalent (backend on a free port, CORS
opened for it): a scripted sequence dispatched directly into
`agent-session-store` (no live LLM call available in this environment —
verification note below) drove `open_paper` → `goto_page` → `set_filters`
correctly through the real DOM and URL bar, and the real browser back/
forward buttons round-tripped the exact view at each step, confirmed via
screenshots attached to the PR.
**Verification gap, accepted:** no `ANTHROPIC_API_KEY`/`OPENROUTER_API_KEY`
was available in this environment, so no real agent turn (and therefore no
real SSE-delivered `ui_action` sequence) was driven end-to-end; the live
verification above dispatched the same event shapes the SSE stream would
carry directly into the store (identical to what `tests/use-drive-ui.test.ts`
does in jsdom, just against the real browser/router instead). The coordinator
confirms a real `just serve` scripted/replay-turn smoke before merge per the
task brief.
Spec updated: no (§4c decision 2 already names the `ui_action` → viewer-store
→ URL contract this PR builds; this entry is #32's implementation contract,
same category as the #29 entry below it).

---

## 2026-07-09 — Viewer (#29): pdfjs-dist bundled dep (D-1), inverted D9 rung ladder (D-2), §6b/§6c grep-verifiable posture (D-3), plus three implementation fill-ins

**Context:** #29's task brief handed down three coordinator decisions to
build against (D-1/D-2/D-3, not open questions) plus a wiring gap
(`agent-session-store.ts` citation capture). Building it surfaced three
further implementation details, all recorded together since they land in
the same PR.

**D-1 — `pdfjs-dist` bundled as a real dependency (not the mockup's CDN
`<script>`).** Dependency gate (all numbers measured 2026-07-09):
*Popular:* 85,074,644 npm downloads in the last 30 days
(api.npmjs.org/downloads/point/last-month/pdfjs-dist); 53,551 GitHub stars
(mozilla/pdf.js). *Maintained:* latest release 6.1.200 uploaded 2026-06-27
(npm), repo last pushed 2026-07-07 (GitHub API, one day before this PR) —
Mozilla org, human-reviewed merges (maintainers list: ydelendik, cdenizet,
brendandahl + Mozilla release automation). *Security:* `pnpm audit` after
install shows one pre-existing, unrelated advisory (`postcss` <8.5.10 via
`next>postcss`, GHSA-qx2v-qp2m-jg93) already on `main` before this PR —
`pdfjs-dist` itself introduces no new advisory and no new peer-dependency
warning (`pnpm peers check`, confirmed before/after). *Pinned:* `^6.1.200`
(matches this codebase's existing convention — every other `frontend/`
dependency uses a caret range, not an exact pin; the lockfile pins the
resolved version regardless). **PASS.**
The worker script (`pdf.worker.min.mjs`) is bundled via
`new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url)`, resolved
by Turbopack into a hashed static asset under `_next/static/media/` — no
CDN request at runtime, verified live (network tab shows the worker served
from `localhost`, the PDF bytes themselves from `arxiv.org` directly).
**A load-bearing correction to how it's imported, found by `pnpm build`
(not caught by `pnpm dev`/tests):** a static top-level `import ... from
"pdfjs-dist"` evaluates the module — including its browser-only globals
(`DOMMatrix` et al.) — at IMPORT TIME, not call time. Next's static export
(D13) prerenders every client component's module once, server-side, to
produce the initial HTML; that prerender pass has no `DOMMatrix`, so the
build failed (`ReferenceError: DOMMatrix is not defined`) even though
`arxiv-pdf-frame.tsx` is a `"use client"` component and the code path that
actually USES pdf.js only runs inside a `useEffect` (client-only by
definition). Fixed by deferring the import itself: `arxiv-pdf-frame.tsx`
keeps only a type-only `import type { PDFDocumentProxy } from "pdfjs-dist"`
at the top (erased at build, no runtime evaluation) and dynamically
`import("pdfjs-dist")`s (cached in a module-level promise) from inside the
rung-2 effect, so the browser-only module never evaluates during SSR
prerender. `pnpm build` (Turbopack) now succeeds and was verified against
real corpus data (see Consequence).

**D-2 — Rung ladder inverted and isolated to `arxiv-pdf-frame.tsx`: default
rung 2 (PDF.js direct fetch), rung 1 (iframe) is a manual fallback, rung 3
(excerpts-only + "open on arXiv") is automatic.** Matches D9's own
"Observed 2026-07-04" note (embedded webviews without a native PDF plugin
turn an iframe PDF load into a download) and the task brief's explicit
default. `rung` is component-local `useState` (not `viewer-store` — the
brief's own instruction: "it's a render fallback, not shareable/URL
state"), reset per-paper via `key={paper}` at the `paper-split-view.tsx`
call site (a fresh mount resets all local state cleanly) rather than an
effect calling `setRung` synchronously on `idv` change — the latter is an
anti-pattern the linter (`react-hooks/set-state-in-effect`) flags directly
("calling setState synchronously within an effect can trigger cascading
renders"); `key`-driven remount is the idiomatic fix, not a suppression.
Rung 2→3 is automatic (PDF.js's own `getDocument(...).promise` rejects →
`setRung(3)`; nothing else to try client-side). Rung 1↔2 is a manual toggle
button (mirrors `docs/mockup.html`'s `rungBtn`); rung 1's own failure has no
reliable programmatic detection (`<iframe onError>` doesn't fire for
HTTP-level failures cross-origin — a known browser limitation, not a gap in
this code) — an accepted limitation matching D9's own "Risks accepted"
section, not a new one.

**D-3 — §6b/§6c grep-verifiable: never proxied, always version-pinned,
always link-back.** `arxivPdfUrl(arxivId, version)` is the single URL
builder (`arxiv.org/pdf/<id><version>`, version NULL → unpinned fallback)
used by BOTH rung 2's `getDocument({url})` call and rung 1's iframe `src` —
one function, not two constructed URLs that could drift. Verified live
against the real corpus (`0704.0217`, version `v2`): the browser's own
network tab shows `GET https://arxiv.org/pdf/0704.0217v2` (200) for rung 2
and the rung-1 iframe's `src` inspected via devtools is the identical
pinned URL — no request to our own server ever carries PDF bytes.
`paper-split-view.tsx`'s header renders the abs-page link and "open on
arXiv" button from `paper` (the arxiv id) alone, independent of whether the
paper-detail fetch has resolved, errored, or is still pending — test-first
(`tests/paper-split-view.test.tsx`) covers all three states.
`cited-excerpts-pane.tsx` takes only `excerpts`/`excerptsTruncated` as
props (both server-capped, §6c row 4/D-1 from #27) and fetches nothing
itself — there is no prop, import, or fetch call in that file that could
carry more than what `GET /api/papers/{id}?chunks=` already capped,
test-first (`tests/cited-excerpts-pane.test.tsx`).

**Fill-in 1 — the URL-sync subscription (D-2 from #28) moves to
`app/page.tsx`, spanning the explorer<->viewer swap.** `explorer-panel.tsx`
previously owned the sole `useViewerUrlSync()` call. Once `paper-split-view.tsx`
exists and `app/page.tsx` swaps between the two regions on `viewer-store`'s
`paper`, `explorer-panel.tsx` itself starts mounting/unmounting as `paper`
toggles — and the sync owner cannot live on a component that unmounts as a
DIRECT CONSEQUENCE of the very store change it exists to react to. Concretely:
a row click's `setPaper` sets `paper` in the store, which (a) is what the
sync effect needs to see to push the new `?paper=` URL, and (b) is also what
`app/page.tsx` uses to decide to unmount `ExplorerPanel` in favor of
`PaperSplitView`. If (b) happens in the same commit as the render that would
have run (a)'s effect, the effect's cleanup fires before its body ever runs
for that update, and the URL push never happens — the open-paper action
silently fails to update the URL. This is the same class of bug as #28's
own cross-tick carry-over note (DECISIONS.md, "apply open-paper + goto-page
in ONE store update") one level up: not two coalesced writes racing, but the
SYNC OWNER ITSELF getting unmounted mid-reaction. Fixed by hoisting the one
`useViewerUrlSync()` call to a small `AppRegion` component defined directly
in `app/page.tsx` (the file the task brief named for "explorer<->viewer
swap") — it never unmounts once the shell renders, so it's the only place
in the tree safe to own the subscription. `explorer-panel.tsx`'s docstring
updated to state why it no longer owns this.

**Fill-in 2 — grid/flex height chain needed explicit `h-full`/`min-h-0` at
every level, not just the outermost container.** Live-testing-only bug (not
caught by any unit test, since jsdom has no real layout engine): the first
version bounded only the OUTERMOST split-view container
(`flex-1 min-h-0` on the grid wrapping the PDF pane + excerpts pane). A CSS
grid's implicit row track defaults to `auto` sizing — it grows to fit its
TALLEST item's content rather than being capped to the grid container's own
height, so `arxiv-pdf-frame.tsx`'s many stacked page placeholders (a
17-page paper renders ~17 divs, each hundreds of px tall) grew the grid
row, which grew the whole document, and the BROWSER WINDOW scrolled instead
of the PDF pane's own `overflow-auto` region — the citation-driven
`scrollIntoView` calls it correctly, but on a container with no actual
internal overflow (nothing to scroll internally when the "scrollable"
element itself has grown to fit all its content). Fixed by adding explicit
`h-full` (not just `flex-1`) at the grid container AND `h-full min-h-0` on
both grid children (`arxiv-pdf-frame.tsx`'s root, `cited-excerpts-pane.tsx`'s
`<aside>`) and on the grid's loading/error placeholder variants — every
level of the chain now has a definite height to stretch into, so only the
innermost `overflow-auto` divs actually scroll. Verified live against real
corpus data (`0704.0217`, 17 pages): a `?page=17` deep link lands the PDF
pane's own scroll position near the end of the document (confirmed via the
page-number badge/nav settling on `p.16-17 / 17` with real rendered page
content — references + author bios, not the title page) while the outer
page/window never scrolls.

**Alternatives rejected:** keeping `viewer-store` `page` writes for
free-scroll/prev-next navigation inside `arxiv-pdf-frame.tsx` (the task
brief's own instruction: this is render-fallback state, not shareable — a
URL that changed on every scroll tick would spam history and contradicts
#28's own debounce posture); detecting rung-1 iframe failure by polling
`iframe.contentDocument` (blocked by cross-origin restrictions — arxiv.org
does not grant same-origin access — so there is no reliable signal beyond
the accepted `onError`-only best effort).

**Consequence:** `pnpm test` (79/79), `pnpm lint`, `pnpm typecheck`,
`pnpm format:check` (this PR's files only — `openapi.json`'s pre-existing
formatting drift predates this PR and is untouched), `pnpm gen:api:check`
(no drift) all clean. `pnpm build` (real Turbopack production build, not
blocked by the worktree's node_modules-symlink artifact after replacing it
with a local install for this worktree only — see PR body) succeeds and was
smoke-tested against the real `corpus.db` + a locally run `just serve`
(CORS opened for the dev origin via `ASKRAG_CORS_ALLOWED_ORIGINS`, a
pre-existing #26 dev-setup knob, not a new one). Safari/WebKit and iOS are
UNVERIFIED (spec §10, carried forward — only Chrome was available to test
against here). The site-footer arXiv attribution + takedown link (CLAUDE.md
hard constraint, §6b item 2) does not exist anywhere in the app yet — a
pre-existing gap from an earlier issue, out of this issue's Build list;
flagged to the coordinator rather than built here to avoid scope creep.
Spec updated: no (D9 already covers the rung ladder and version-pinning
decision; this entry is #29's implementation contract, same category as the
#27/#28 entries below it).

---

## 2026-07-09 — Explorer UI (#28 PR review round 1): URL-sync classifier keyed on the store, not the lagging URL

**Context:** review round 1 on PR #68 found a [major] in
`hooks/use-viewer-url-sync.ts`: the effect classified a mismatch between the
live URL and the store as "external" whenever `urlString !== lastSynced`,
where `lastSynced` was set to the PUSH TARGET at push time. `router.push` is
async — `searchParams` doesn't reflect the pushed URL until Next commits the
navigation, often several ticks later. A second store-driven change landing
inside that window recomputed `storeString` (now reflecting both changes)
but compared it against a `urlString` that still lagged the FIRST push, not
the current store — `urlString !== lastSynced` was true for the wrong
reason, misclassifying the second change as an external URL change and
calling `hydrateFromUrl` against the stale URL, which reverted the store and
dropped the second change. Reviewer's repro: click category (pushes,
`lastSynced="category=cs.CL"`, `searchParams` still lags at "") then
immediately `setPaper` before the navigation commits — the second effect run
sees `urlString=""`, `storeString="category=cs.CL&paper=…"`,
`lastSynced="category=cs.CL"`, wrongly hydrates from `""`, losing both the
open-paper and (transiently) the category. Latent for human clicks today
(sub-frame window, every high-frequency input already debounced) but
directly reachable once #29 drives this hook programmatically via
`drive_ui` across ticks.
**Decision:** classify by comparing the current store-derived string against
`prevStoreString` — what the STORE said the last time this effect ran —
instead of comparing the live URL against the hook's own last push target.
A mismatch there can only mean the store changed since the last run (this
hook is the sole reader/writer of `prevStoreString`), so it's unambiguously
store-driven regardless of whether `searchParams` has caught up to any
earlier push. `prevStoreString` is seeded from the CURRENT store on mount
(not `""`/`null`), which is what keeps the original initial-mount case
correct: a URL with params against a still-default store reads as "the
store hasn't changed" -> external -> hydrate, not a spurious push that would
overwrite the URL's params with the (still-default) store.
**Verification:** reproduced the reviewer's exact scenario live (rapid
category-click + row-click fired in the same tick, no round-trip between
them) against the real corpus.db-backed API — both changes now land
correctly (`?category=cs.CL&paper=<id>`, confirmed settled and via a
subsequent back-button step), where the pre-fix classifier would have
dropped one.
**Alternatives rejected:** debouncing/coalescing rapid `router.push` calls
into one — doesn't fix the underlying misclassification (a single push can
still race a still-lagging `searchParams` against an EARLIER push if two
land within one Next commit cycle), and adds latency to every filter/search
interaction for a problem that isn't about push frequency.
**Nits judged, not fixed:** (1) a hand-edited URL with non-canonical param
order round-trips to canonical order on first hydrate, costing one extra
history entry that self-normalizes — reviewer's own analysis already scoped
this to near-zero blast radius (app-generated URLs are always canonical);
fixing it would need semantic (parsed) equality instead of string equality
in the classifier, complexity not justified by the risk. (2) store-defaults-
then-hydrate costs one wasted initial browse fetch before a shared search
link's filters apply — inherent to a module-level zustand store (created at
import time, before any component's `searchParams` exists to seed from);
fixing needs a bigger initialization redesign, out of scope for a review nit.
(3) `tests/viewer-store.test.ts` gained a direct `setPage` assertion (cheap,
fixed).
**Consequence:** `hooks/use-viewer-url-sync.ts` rewritten; `pnpm test`
(56/56), `typecheck`, `lint`, `format:check` all clean.
Spec updated: no (implementation contract for #28, same category as the
entry below it).

---

## 2026-07-09 — Explorer UI (#28): infinite-scroll virtualized table, URL-as-source-of-truth filters, data-gated rigor column, plus two fill-ins

**Context:** #28's task brief handed down three coordinator decisions to
build against (not open questions): D-1 infinite scroll, D-2 URL-is-source-
of-truth, D-3 no-empty-column. Building D-2 surfaced two implementation
details the brief left open.

**D-1 — Infinite scroll via `useInfiniteQuery` + TanStack Virtual.**
`hooks/use-papers-query.ts`'s `usePapersQuery` wraps `GET /api/papers` in
`useInfiniteQuery` (`getNextPageParam: (page) => page.next_cursor`);
`components/explorer/paper-table.tsx` flattens accumulated pages, renders
only the windowed rows TanStack Virtual computes, and calls `fetchNextPage()`
once the last rendered row is within `FETCH_NEXT_THRESHOLD` (8) rows of the
loaded end — never all 6,460 at once, matching #27's own bounded-search-k
posture on the backend side.
A live-testing-only bug (only visible against real corpus data, not the
store test): the first version used a real `<table>` with a fixed-height
absolutely-positioned `<tr>` per virtual row. Two independent failures
followed: (1) fixed `estimateSize` assumed every row was the same height,
but paper titles range from one word to a full wrapped paragraph — a row
taller than the estimate overlapped its neighbor, since absolute positioning
doesn't push siblings down. (2) each absolutely-positioned `<tr>` was given
`display: table` so its own cells would size themselves, but that makes
every row an independent table layout context sized by ITS OWN content,
never matching the `<thead>`'s column widths — headers and body columns
drifted out of alignment. Fixed by dropping the `<table>` element entirely
in favor of `role="table"`/`role="row"`/`role="cell"` flex divs with an
explicit `COLUMN_WIDTH_PX` map shared verbatim between the header and every
body row (TanStack Virtual's own documented pattern for a virtualized
table), and dynamic row measurement (`ref={virtualizer.measureElement}`)
instead of a fixed height, so `estimateSize` only seeds the initial layout
before the real per-row height is measured.

**D-2 — URL is the source of truth; the store derives from it.**
`stores/viewer-store.ts` holds plain state (`q`/`category`/`yearFrom`/
`yearTo`/`sort`/`paper`/`page`) plus two PURE functions,
`viewerStateFromSearchParams`/`searchParamsFromViewerState` — no
`next/navigation` import in this file, so both directions are directly unit
tested (`tests/viewer-store.test.ts`, the acceptance gate) without mounting a
router. Default/empty values are never written to the URL (`q=`,
`category=null`), which is what makes the round trip exact rather than
merely lossless.
**Fill-in 1 — the router glue is a separate hook, `hooks/use-viewer-url-sync.ts`,
not in the store, is ONE effect, not two, and pushes (not replaces) history.**
`useRouter`/`usePathname`/`useSearchParams` are component-bound hooks; a
zustand store file can't call them. A first version split URL->store and
store->URL into two effects; on initial mount with URL params already
present, the store->URL effect ran with a STALE pre-hydration closure in the
same passive-effect flush right after the URL->store effect's
`hydrateFromUrl` call (the zustand state update schedules a re-render, it
isn't synchronous, so the second effect's captured filter fields were still
the old defaults) — it would push the just-hydrated params away, then
self-correct one render later on the following flush. Collapsed into one
effect that computes both the raw URL string and the store-derived URL
string every run and makes an ATOMIC decision: equal -> no-op; URL differs
from the last string this hook itself produced -> treat as an external URL
change and hydrate; otherwise -> treat as a store-driven change and write the
URL. The `lastSynced` ref stays local to the hook, not the store, since the
store's own tests need no router.
A second, live-testing-only finding on the SAME hook: it originally called
`router.replace`, reasoned (wrongly) as "filtering shouldn't spam history."
Manually driving the running app (Playwright/browser tooling) showed this
broke the browser back button outright — every filter click OVERWRITES the
current history entry, so back from any filtered view exits the app
entirely, contradicting §4c decision 2's explicit "shareable/back-button
friendly" requirement in the very sentence that motivates URL-as-state at
all. Switched to `router.push`. History-spam is instead prevented at the
INPUT layer: `corpus-search-bar.tsx`'s `q` was already debounced (300ms);
`facet-filters.tsx`'s year `from`/`to` inputs gained the identical debounce
pattern (`useDebouncedYearInput`, 400ms) so typing a year doesn't push one
history entry per keystroke. Category-button and row clicks were already
one push per deliberate click, needing no debounce.
**Fill-in 2 — a composition component, `components/explorer/explorer-panel.tsx`,**
mirrors `chat-panel.tsx`'s role for the agent panel: mounts
`facet-filters.tsx` + `corpus-search-bar.tsx` + `paper-table.tsx` and owns
the single `useViewerUrlSync()` call, so `app/page.tsx` stays the two-region
shell (`§4c`: "the app: explorer + viewer + agent panel composition") without
itself becoming a client component full of hook wiring. Wrapped in
`<Suspense>` in `page.tsx` because `useSearchParams` requires a boundary
under `output: 'export'`.

**D-3 — no column backed by empty data.** `paper-table.tsx` computes
`hasRigorData = papers.some(p => p.facets?.venue_rigor != null)` over the
currently loaded rows and only pushes the Rigor column onto the TanStack
Table `columns` array when true — read from real response data, not a
guessed dev/prod flag, so the column appears automatically once #13's embed
run populates `venue_rigor` in a given environment. `venue_rigor` is a
continuous 0..1 score (spec §1), not the mockup's placeholder 0-3 integer;
`rigorDots()` maps it onto the mockup's 3-dot display
(`Math.round(score * 3)`), a display heuristic only, not a spec-defined
discretization.

**Alternatives rejected:** an `?sort=` UI control as its own component —
the issue's Build list names no such file, mockup.html has none either, and
the store/URL/backend contract for `sort` is already exercised by
`viewer-store.test.ts`; instead the Year/Paper column headers in
`paper-table.tsx` toggle `year_desc`/`year_asc`/`title_asc` on click, giving
`sort` a real UI surface without inventing an unscoped component. A
draggable/clickable year-band histogram (mockup's decorative bars, made
interactive) — the mockup's own version is `aria-hidden` decoration, not a
control; `facet-filters.tsx` keeps the bars decorative and adds two plain
number inputs (`year_from`/`year_to`) for the actual filter, which round-
trips through the URL identically at a fraction of the complexity.
Putting the store<->URL sync ref state inside `viewer-store.ts` itself
(rejected in Fill-in 1) — would make the store's own tests router-dependent
for no benefit, since the pure functions are what the acceptance gate needs.

**Consequence:** `tests/viewer-store.test.ts` (new, 55 total frontend tests
passing) proves the store⇄URL symmetry gate both directions plus every
store action; `pnpm lint`/`pnpm typecheck` clean. `pnpm build` (Turbopack)
fails in the implementor's git worktree ONLY with a `node_modules` symlink-
out-of-filesystem-root Turbopack panic — a worktree artifact (this repo's
own `.worktrees/` isolation scheme symlinks `node_modules` in), not a code
issue; the coordinator confirms a real Turbopack build outside the worktree
before merge. No column ever shows `score` (fused retrieval score) since it
is `null` on every browse-mode row — the same D-3 "no empty column"
reasoning applied one column further than the rigor case the issue named
explicitly.
Spec updated: no (§4c already names `paper-table.tsx`/`facet-filters.tsx`/
`corpus-search-bar.tsx`/`use-papers-query.ts`/`viewer-store.ts`/
`viewer-store.test.ts`; this entry is #28's implementation contract, same
category as the #27 entry below it).

---

## 2026-07-09 — Explorer API (#27): citation contract (D-1) + shared facet SQL (D-2), plus three implementation-contract fill-ins

**Context:** #27's task brief handed down two coordinator decisions to build
against (not open questions) and left several querystring/design details for
the implementor to resolve. All five are recorded together since they land
in the same PR and several interact.

**D-1 — Citation contract (ids on the wire, text only from the capped
endpoint).** The SSE `done` event now carries `citations:
[{paper_id, chunk_ids: [...]}]`. Mechanism: `traces.ToolCallRecord` gains a
`citations: tuple[Citation, ...]` field (`Citation(paper_id, chunk_id)`,
ids only — same posture the record already held for its own result: no
payload, ever). `askrag/agent/loop.py`'s `_dispatch_tool_calls` populates it
via a new `_citations_of(name, result)`, special-cased for `search_corpus`
only (mirrors `sse_events.translate()`'s pre-existing `name == "drive_ui"`
special-case — "know one tool's shape at the translation boundary," not a
new general interface). `sse_events.py` gains `Citation(paper_id,
chunk_ids)` (the wire shape) and `citations_from_tool_calls()`, a single
aggregator (dedupe + group by paper_id, first-seen order) that both
`done_event()` (live turns) and `replay.py` (showcase replays) call, so a
replayed turn's citations can never drift from a live one's.
**Known gap, accepted:** `read_paper` produces no citations — its
`TextSpan` result has no `chunk_id` (page-range reads, not chunk-keyed), so
a deep-read via `read_paper` alone can't drive the cited-excerpts pane, only
`search_corpus` hits can. Fixing this needs a `read_paper.py` schema change
(adding `chunk_id` to `TextSpan` + its SQL) that's out of #27's Build list;
revisit if evals or usage show `read_paper`-only answers citing papers the
frontend can't resolve to excerpts.
**Alternatives rejected:** computing citations from the model's raw answer
text via a regex/id-extraction pass (cli.py's `_verify_citations` pattern)
— would conflate "the model wrote this id in prose" with "the model actually
retrieved this chunk," the exact ambiguity #31's `ui_action` reconciliation
already exists to avoid one layer up; extending `read_paper` to also carry
citations now — speculative before a real gap is measured, and the fix
touches a different tool's schema than this issue's Build list names.

**D-2 — Facet SQL lives once.** Extracted into `askrag/facets.py` (new,
top-level module — mirrors `traces.py`'s existing pattern of a single
well-named top-level file for a cross-layer concern, rather than nesting
under `retrieval/` (implies ranked search, wrong fit) or `tools/`
(query_metadata is one of two consumers, not the owner)). Holds
`GROUP_BY_COLUMNS`, `where_clause()`, `count_scalar()`, `count_grouped()` —
one `{name -> column}` map, one WHERE-builder, one GROUP BY query template.
`query_metadata.py`'s `_run_count_papers` now calls these instead of owning
its own copy; `GET /api/facets` and the papers list's `facets=` scoping (see
below) call the same functions with their own `max_groups` — a parameter,
never a forked query, per the task brief's own instruction.

**Fill-in 1 — `/api/papers`'s `q` always goes through hybrid retrieval, no
separate keyword-only mode.** The issue's querystring sketch listed
"semantic q via retrieval, keyword via FTS" as two capabilities to wrap;
read literally as two simultaneous request modes there'd be no second `q`
parameter to pick between them. `HybridSearch.search()` (D8) already fuses
vector+BM25 and degrades gracefully to BM25-only if the vector leg is down
— it already IS "keyword via FTS" as a fallback, not a separate mode a
client selects. `/api/papers?q=` calls it once; `retrieval/fts.py` needs no
new route-level exposure.
**Alternatives rejected:** a `mode=semantic|keyword` toggle — invents a
knob nobody asked for and duplicates a decision `HybridSearch` already
makes (D8's fail-soft degrade), the kind of speculative option the
engineering principles caution against.

**Fill-in 2 — `facets=` on `/api/papers` means the FIVE DIVERSITY-SCORE
columns (§1: authority/niche_idf/author_novelty/revisions/venue_rigor), a
DIFFERENT sense of "facet" than `/api/facets`'s categorical counts.** The
spec names both senses "facet" (§1's corpus description vs. the mockup's
category-filter rail / `query_metadata`'s group-by). `GET /api/facets` (D-2)
is tied to the categorical sense by the coordinator's own note referencing
`count_papers group_by`. `facets=` requests a comma-separated subset of the
five score columns to include per row (`PaperListItem.facets`/
`PaperDetailResponse.facets`); unknown names are a 400. The overlap in
naming is real, not a typo — documented in `routes_explorer.py`'s module
docstring and here rather than renamed away, since both senses are already
load-bearing (categorical facets drive `/api/facets` and `query_metadata`;
diversity facets are named in spec §1 and stored in `papers` since #14).

**Fill-in 3 — cursor design: real SQL keyset for browse, bounded-list
position cursor for search.** The issue's own acceptance line ("cursor
pagination correct; p95 < 100 ms on metadata-only queries") only measures
the `q`-empty path, so that's where a true SQL keyset (`WHERE (col OP ? OR
(col = ? AND arxiv_id > ?))`, `arxiv_id` as stable tiebreak) earns its
complexity. The `q`-set path calls `HybridSearch.search()` once for a
BOUNDED `explorer_search_k` (config, default 100) result, collapses
chunks→papers (dedup by paper_id, first-seen = best fused score since
`HybridSearch.search()` already returns rank-descending), then paginates
that one already-fetched, deterministically-ordered list by cursor
POSITION (find the last-seen id, slice after it) rather than re-running
search with a larger `k` per page. Retrieval fundamentally returns a
bounded top-k, not an arbitrarily-deep ranked table (D8) — there is no
"page 50 of a semantic search" to keyset into. The cursor is one opaque
base64(JSON) shape either way (`q`/filters/`sort`/`last_key`/`last_id`);
a cursor whose encoded q/filters/sort don't match the current request is
rejected (400) rather than silently reinterpreted.
**Alternatives rejected:** re-running `HybridSearch.search()` with an
increasing `k` per page (defeats "bounded," and re-embeds the query on
every page for no correctness gain); OFFSET pagination on the search path
(the exact anti-pattern "keyset, not OFFSET" — though the underlying bound
is already small here, position-slicing an already-fetched list is free
where OFFSET against a growing scan would not be).

**Consequence:** `tests/test_facets.py` (new), `tests/test_routes_explorer.py`
(new, §6c rows test-first per the issue's instruction), and
`tests/test_query_metadata.py` (unchanged — behavior preserved by
construction) all pass; `test_sse_events.py`/`test_replay.py`/`test_loop.py`/
`test_traces.py` updated for the new `citations` field;
`frontend/lib/sse.ts`/`tests/sse.test.ts` mirror `DoneEvent.citations` in
lockstep. `GET /api/facets` applies its `category`/`year_from`/`year_to`
filters uniformly across all four output dimensions (no "still-available-
options" exclude-own-dimension faceting, e.g. a `category=cs.CL` request's
own `category` breakdown just shows `{cs.CL: total}`) — a v1 simplification
worth revisiting once the frontend's facet rail (#33+) needs it.
`get_hybrid_search_factory` (routes_explorer.py) constructs a fresh
`HybridSearch` per search request rather than sharing one cached instance —
mirrors `tools/search_corpus.py`'s pre-existing pattern (no shared instance
exists anywhere in the codebase yet), not a new gap this PR introduces;
worth a shared instance on `app.state` (like `SessionStore`) as a follow-up
if query-time cold-load latency on the search path is ever measured and
matters — out of scope here since the issue's own p95 bar is metadata-only.
Spec updated: no (§4c already names `routes_explorer.py`'s three routes and
the §6c/§6b posture they implement; this entry is #27's implementation
contract, same category as the #31 entry above it).

---

## 2026-07-09 — Agent panel (#31, round 2): session mode split from turn lifecycle in `agent-session-store.ts`

**Context:** round-1 review (Opus) found a [major]: `AgentStatus` originally
had five members — `idle | streaming | tool_running | capped | replay` — per
`.claude/rules/frontend.md`'s state-machine line. `use-agent-stream.ts` set
`status: "replay"` in `onopen` from the `X-AskRAG-Mode` header, but the
replayed stream's own events then flow through `applyEvent`, which
unconditionally reassigns `status` for every `tool_call`/`tool_result_summary`
/`text`/`done` it sees — including the replayed stream's own. The replayed
run's first event (a `tool_call`, confirmed against `replay.py`) clobbered
`status: "replay"` back to `tool_running`, so `ReplayBanner` and the header's
amber dot vanished for the entire replayed answer: a visitor watches a
recorded session with no indication it's recorded, contradicting D11's
honesty intent and `ReplayBanner`'s own docstring. No test caught it because
`agent-session-store.test.ts` exercised `setReplay` in isolation, never
followed by an `applyEvent` call.

**Decision:** split the conflated union into two orthogonal fields:
- `mode: "live" | "replay"` — set once per turn, from the `X-AskRAG-Mode`
  header in `onopen`; reset to `"live"` at the start of every new turn
  (`startTurn`, since `budgets.check()` decides fresh per request); `applyEvent`
  never touches it.
- `status: "idle" | "streaming" | "tool_running" | "capped"` — turn lifecycle,
  owned by `applyEvent` exactly as before. `capped` stays here (unaffected by
  the bug: its 429 path throws before any event is ever applied).

`ReplayBanner` and the panel header's mode dot now read `mode`; the timeline
still reads `status`. Added a store test asserting `mode` survives a full
run of `applyEvent` calls after `setReplay`, and one confirming `startTurn`
resets it to live.

**Alternatives rejected:** having `applyEvent` special-case "don't overwrite
`status` if it's currently `replay`" — keeps the two concerns tangled in one
field and one function, the actual root cause; a future lifecycle addition
would need to remember the same special-case again.

**Consequence:** `.claude/rules/frontend.md`'s state-machine line ("idle /
streaming / tool-running / capped / replay" as one union) is now inaccurate
for this store and is amended in the same PR — the round-1 finding *was* that
conflation, so the fix is a deliberate, documented deviation, not an
oversight. Revisit if a future status kind (e.g. an explicit error state)
turns out to need the same live/replay orthogonality some other lifecycle
value already has.
Spec updated: no (frontend rule amended instead; §4c/D11 unchanged).

---

## 2026-07-08 — traces.db gains `question`/`answer_text` so showcase replays reproduce the answer, not just the timeline (issue #30)

**Context:** #30 builds the chat route's REPLAY branch (D11: the site
degrades to a cached showcase session once the global daily cap is spent).
`traces.Run` carried tool-call records + tokens/cost but no answer text, so
a replay could reconstruct the tool-call timeline but not the final answer
— not "a still-good demo" (D11's own framing), just a timeline with no
punchline.
**Decision:** `runs` gains two `NOT NULL` columns, `question` (the user
message the run answered) and `answer_text` (the turn's final answer —
our own AI-generated text, §6c-compliant, never raw retrieved chunk text).
`traces.Run`, `record_run(...)`, and `_row_to_run` all extend to carry them;
`loop.py`'s `run_turn` (which already calls `record_run` internally) passes
`user_message` and the final `TurnResult.text` through, no other loop
change. `askrag/api/replay.py` reads `answer_text` back out as the
replayed turn's one `text` SSE event.
**Alternatives rejected:** a separate `showcase_answers` table keyed by
`run_id` (D13/§4c: "replays live in traces.db... no separate format, no
second store" — splitting the answer into a second table violates that
decision for no benefit, since every showcase row needs an answer 1:1);
storing the answer only for `showcase=1` rows (adds a conditional-NULL
column and a "how did this showcase get flagged after the fact with no
answer" failure mode — simpler to always capture it, it costs a few KB
per run in a `traces.db` that's already dev/prod ephemeral).
**Consequence:** `traces.db` is dev-only and regenerable (D13/§4c: no
migration path exists or is warranted) — `CREATE TABLE IF NOT EXISTS`
does not retrofit existing local databases, so a pre-#30 `traces.db` must
be deleted/moved aside once, not migrated; a fresh one picks up the new
schema on its first write. `tests/test_traces.py`'s `sample_run` fixture
and every other test file constructing `record_run(...)` calls updated to
pass the two new required fields.
Spec updated: no (§4c's "replays live in traces.db" decision already
covers this; `Run`'s exact column set was never spec-pinned, just the
one-store constraint, which this entry keeps intact).

---

## 2026-07-07 — `ui_action` is advisory/pre-validation, documented explicitly for #26's stream consumer (issue #24 review round 2)

**Context:** review round 1 on PR #64 flagged (non-blocking nit) that
`sse_events.translate()`'s `drive_ui` → `ui_action` mapping fires at
`TOOL_CALL` time on the model's raw args, before `drive_ui.run()` validates
the target against corpus.db — correct behavior per #24's own brief, but the
"treat `ui_action` as provisional, reconcile against the paired
`tool_result_summary`" contract only lived in the PR body, not anywhere a
future consumer would see it.
**Decision:** keep the behavior unchanged; document the contract on
`UiActionEvent` itself (`askrag/api/sse_events.py`) so #26's
`use-agent-stream.ts` inherits it by reading the type it consumes, not by
re-discovering it from a closed PR thread.
**Alternatives rejected:** deferring `ui_action` emission until after
`drive_ui` dispatch validates (would need `TOOL_RESULT`'s `AgentEvent` to
also carry the action's args, a `loop.py` change out of scope for #24 and
unmotivated — the paired `tool_result_summary(ok=False)` already surfaces a
rejected target one event later).
**Consequence:** no code behavior change; `sse_events.py`'s docstring is now
the durable source #26 reads from.
Spec updated: no (process-only; documents an existing, reviewed behavior).

---

## 2026-07-07 — `askrag/cli.py` is the single terminal entrypoint; `loop.main`/`_print_event` retired (issue #24)

**Context:** #23 shipped `loop.py`'s own `main()` + `_print_event()` as a
one-shot smoke CLI (`just smoke-agent`). #24's task brief names the REPL as
milestone 3's exit artifact and directs consolidating onto one CLI rather
than keeping two terminal entrypoints into the same loop.
**Decision:** `askrag/cli.py` is THE terminal entrypoint: no question arg
runs the interactive multi-turn REPL (threading `TurnResult.messages`
between turns, printing a live tool-call timeline via
`askrag.api.sse_events.translate()`, a running session cost, and
corpus.db-verified citations after each answer); one question arg runs a
single one-shot turn. `loop.py`'s `main()` and `_print_event()` are deleted
outright (shed, not aliased) along with the now-unused `argparse`/`sys`/
`telemetry` imports they were the only callers of. `just repl` (new) and
`just smoke-agent` (repointed) both call `askrag.cli` — the smoke recipe's
OpenRouter cheap-first behavior (DECISIONS.md 2026-07-06) is unchanged,
only the module it invokes changed.
**Alternatives rejected:** keeping `loop.main` for one-shot smoke and adding
`cli.py` only for the interactive REPL (two entrypoints into the same loop
that would drift, exactly what "one CLI, one way" exists to prevent).
**Consequence:** `loop.py` no longer prints anything or touches
`telemetry`/`sys`/`argparse` — it is purely the library the CLI (and later
#40's chat route) calls into, which was already its intended shape (D2).
Spec updated: no (process-only; `sse_events.py`/`cli.py` are #24's own
Build-list files, already named in spec §4c).

---

## 2026-07-06 — OpenRouter becomes validation-only (cheap-first smoke); live serving reverts to direct Anthropic/Haiku, superseding 2026-07-05's OpenRouter-as-primary plan (issue #23, owner directive)

**Context:** 2026-07-05's "Live agent LLM: OpenRouter-routed model via env"
entry planned OpenRouter's OpenAI-compatible API as the LIVE agent's primary
provider (replacing D3's Haiku-on-Anthropic plan outright), with reasoning-
block round-tripping as a named build requirement for #22/#23. That wiring
was never built (neither #22 nor this PR touched an OpenAI-compatible
client). The owner redirected before #23 landed: validate the hand-built
loop against a CHEAP model first, keep prod serving on Haiku.
**Decision:** the loop's `ModelClient` seam is `anthropic`-SDK-shaped
throughout — no OpenAI-compatible client exists anywhere. `config.py` gains
`agent_api_base_url` (default `""` ⇒ real Anthropic, D3's Haiku), an
env-only `openrouter_api_key`, and `smoke_model` (`deepseek/deepseek-v4-flash`).
Setting `agent_api_base_url` routes the SAME `anthropic.Anthropic` client at
OpenRouter's **Anthropic-compatible** endpoint (not its OpenAI-compatible
one) — one client, config-only branching, no second SDK, no branching inside
`loop.py` itself (`anthropic_client_from_settings` is the only place that
looks at the setting). Two empirically-resolved integration details, recorded
because the docs left them ambiguous: (1) base_url is
`https://openrouter.ai/api` **without** a trailing `/v1` — the anthropic SDK
appends `/v1/messages` itself, so `.../api/v1` double-`/v1`s to a 404; (2)
auth is `auth_token=` (Bearer) via the SDK, not `api_key=` (x-api-key) —
OpenRouter documents Bearer, Anthropic's native header is x-api-key. Pricing
for cost accounting stays Haiku's (`agent_usd_per_mtok_*`) regardless of
which model actually served a smoke call — the smoke validates loop
plumbing, not billing, so its trace cost is an approximation by design.
Because the loop always appends `response.content` verbatim back into the
next call (the standard Anthropic tool-use round-trip, needed regardless of
provider), the "reasoning blocks must round-trip" requirement from the
superseded plan is satisfied as a side effect of ordinary tool-use handling —
it never needed special-casing once the client is Anthropic-shaped.
**Alternatives rejected:** building the OpenAI-compatible client as
2026-07-05 planned (never implemented; superseded before any code existed,
so there is nothing to migrate away from); smoke-testing directly against
Haiku first (defeats the "cheap-first" point of validating an unbuilt loop
before spending on the prod model).
**Consequence:** the 2026-07-05 "Live agent LLM: OpenRouter-routed model via
env" entry below is superseded — its OpenAI-compatible-API plan for the live
agent does not ship; treat it as historical context, not current behavior.
Running the live smoke needs a real `OPENROUTER_API_KEY` (coordinator/human
step); `just smoke-agent q="..."` documents how. Fake-model tests
(`test_loop.py`) are the PR's actual acceptance gate; the smoke is the
owner's separate confirmation, per the issue's acceptance checklist.
Spec updated: D3 (one-line note: a cheap OpenRouter model validates the loop
before Haiku spend; D3's prod decision — Haiku, direct Anthropic — is
unchanged).

---

## 2026-07-06 — #23 ships only the system-prompt quote-discipline instruction; the server-side ≤3-quote/≤50-word per-answer gate stays #30's job (issue #23)

**Context:** an #23 issue comment (carried forward from #22/#58) called the
per-answer quote-accounting gate a "hard acceptance gate... not optional" for
this issue. The 2026-07-06 `read_paper` DECISIONS.md entry (below) already
moved that cap downstream to "answer-assembly (#23/#30)" once `read_paper`'s
own tool-level cap was removed as contradicting §6c row 1/D1. #23's own task
brief scopes the server-side gate out explicitly: building it needs verified
citations (which answer-assembly, not the loop, produces) and the issue's
own **Build** list names only `prompts.py`/`context_window.py`/`loop.py`.
**Decision:** #23 implements the quote-discipline **instruction** only
(`prompts.py`'s QUOTES paragraph: prefer paraphrase, keep verbatim quotes
short and quoted). It does NOT implement per-answer/per-conversation
quote-count enforcement — there is no answer-assembly stage in this PR to
enforce it in. The hard, server-side ≤3-quotes-per-paper/≤50-word cap (§6c
row 4) remains #30's responsibility, unchanged from the `read_paper` entry.
**Alternatives rejected:** bolting quote-counting onto `loop.py` now (the
loop only ever sees one turn's raw tool results, not an assembled answer with
resolved citations — the same reasoning the `read_paper` entry already used
to reject enforcing it at the tool boundary applies here too, one level up).
**Consequence:** none of this PR's user-facing surfaces exist yet (no route,
no frontend), so there is no shippable path that could return an unguarded
quote today; the gate is still required before #30 exposes one. Noted here
so the boundary is explicit rather than inferred from silence.
Spec updated: no (§6c's clarifying note already covers this from the
`read_paper` side; this entry just confirms #23 doesn't build the other end).

---

## 2026-07-06 — Agent loop context window: evict-only, not evict-then-summarize (issue #23)

**Context:** issue #23 named "evict/summarize stale tool results" as the
context-window mechanism without picking one.
**Decision:** v1 evicts only — the oldest still-live `tool_result` block is
replaced with a short `[evicted: earlier <tool> result]` stub, one block at a
time, until the running estimate fits `message_token_budget` or nothing
evictable remains. Summarization is not built.
**Alternatives rejected:** evict-then-summarize (an LLM call to summarize
stale context needs the model client mid-eviction, which breaks the
API-free test story — house rule, tests never call an LLM — and spends part
of the very token/cost budget the mechanism exists to protect); a rolling
window by message count instead of tokens (message count doesn't track
actual context cost — a single `read_paper` result can be worth many short
turns).
**Consequence:** `test_context_window.py` covers oldest-first ordering, the
current-turn/system-prompt exclusion, and the "nothing left to evict"
termination case. A pathological turn can still end up over budget once
every tool_result is stubbed — accepted, because `max_tool_steps_per_message`
is the real backstop against runaway turns, not eviction.
**Revisit trigger:** eviction demonstrably drops context an answer needed
(measured via eval failures traceable to a stubbed-out tool result).
Spec updated: no (D1/D2 already name "evict/summarize" as the mechanism
class; this entry just resolves which one v1 ships).

---

## 2026-07-06 — query_metadata prefactor: enum'd shapes replace raw model SQL, done before #23 (issue #60)

**Context:** #23's agent loop is about to become `query_metadata`'s first
model-facing consumer. Four reasons converged to reshape the tool before that
wiring happens rather than after: **security** — raw model SQL had already
produced a `randomblob` DoS (#57 review finding) and a blob-literal JSON crash
(#59 review finding); **portability** — the safety model was welded to sqlite
primitives (`set_authorizer`/`set_progress_handler`) with no Postgres analog,
blocking the D4 pgvector migration seam; **reliability** — an LLM authoring
SQL is error-prone where a typed op it picks from a closed menu is used
correctly; **clarity** — mirroring `drive_ui`'s existing discriminated-union
pattern is simpler than the authorizer/progress-handler machinery it replaces.
**Decision:** `query_metadata` is now a `drive_ui`-style `RootModel` over a
`Field(discriminator="op")` union of exactly three ops — `count_papers`
(filters: `category`/`year_min`/`year_max`/`has_license`; optional
`group_by: Literal["category","year","license","venue"]` resolving through a
server-side `{Literal -> column}` map, never string-interpolated; `None` →
scalar count, else → a top-N-bounded histogram), `paper_facets` (point lookup
by `paper_id` → title/primary_category/year/version/license/venue/n_chunks/
n_pages, raises on unknown id), `corpus_stats` (no params → n_papers/n_chunks/
year_min/year_max/n_categories). Every op runs one fixed parameterized SQL
template; there is no model-authored SQL path anywhere. Per-op frozen
dataclass results (`CountPapersResult | PaperFacetsResult | CorpusStatsResult`),
each with `to_model_payload()` (the #58 pattern). DELETED entirely, no
back-compat: `_make_authorizer`/`set_authorizer`/the `SQLITE_FUNCTION`
allow-list, `set_progress_handler` + its deadline, single-statement reliance,
`QueryMetadataArgs(sql=...)`, `_json_safe_cell`. Dead config removed:
`query_metadata_allowed_functions`, `query_metadata_timeout_seconds`;
`query_metadata_max_rows` repurposed and renamed
`query_metadata_histogram_max_groups` (the histogram top-N ceiling — the only
row-returning shape left to cap). The `mode=ro` corpus connection stays
(cheap defense-in-depth); with no model-authored SQL the injection/DoS surface
is gone by construction, not by a guard against it.
**Alternatives rejected:** keeping the authorizer/timeout machinery alongside
the new enum'd ops "just in case" (redundant — there is no SQL path left for
it to guard, and an unused security mechanism is itself a maintenance
liability); a fourth `list_papers` shape (speculative — not in the certain
core the issue named; further shapes are evidence-driven from #23's real
usage per the issue's "evidence-driven growth" note, never guessed).
**Consequence:** `tests/test_query_metadata.py` is fully rewritten — the old
SQL-injection/DoS-refusal tests are deleted (moot, no SQL surface); new tests
cover per-op correctness (scalar + histogram + facets + stats), filter
binding, off-enum `group_by` rejected by pydantic before execution, unknown
`paper_id` raising, and the union rejecting a free-form/`sql` field. `#23`
carries the evidence-channel note: its eval system prompt should invite the
model to state any metadata query it wished it had: recurring wishes get
promoted to new typed union variants later, never back to raw SQL.
Spec updated: §5 (`query_metadata` row rewritten: enum'd ops, no model SQL),
§6 (the "SQL injection (ish)" threat vector retired — replaced with "N/A",
enum'd parameterized shapes only).

---

## 2026-07-06 — §6c enforcement relocated: read_paper is the model-read path, not the verbatim-cap enforcer (owner directive, issue #58)

**Context:** the 2026-07-06 retrieval+tools coherence checkpoint (finding 1)
found `read_paper` applying the ANSWER/display cap (`quote_max_words=50`,
`max_quotes_per_paper=3`, §6c row 4) at the MODEL-facing tool boundary, so one
call returned ≤~150 words — contradicting §6c row 1 ("the model may read full
text via `read_paper`") and D1 ("read a specific paper deeper"), and
inconsistent with `search_corpus`, which already hands the model full
~1000-token chunks uncapped.
**Decision:** `read_paper` returns a page-ordered prefix of a paper's chunks
bounded by a new `read_paper_max_tokens` setting (default 16,000 — ≈20% of
`message_token_budget`, sized to cover a full short arXiv CS paper's chunks or
a substantial page range of a longer one while leaving room for further tool
calls in the same message). The ≤50-word/≤3-quote cap is removed from
`read_paper` entirely; it is NOT this tool's job. That cap governs verbatim
quotes surfacing in an ANSWER (§6c row 4) and moves downstream to
answer-assembly (#23/#30) and the frontend (#26), where it is now the hard
gate — §6b is unchanged throughout (extracted text from corpus.db only, never
PDF bytes).
**Alternatives rejected:** raising the tool's word cap instead of removing it
(still couples a display posture to a read tool, and any fixed word number is
arbitrary where a token budget maps directly to the model's real read cost);
leaving the cap at both the tool and answer-assembly (redundant enforcement
invites the two points drifting apart, and the tool-level cap was already
measured to cripple deep-read, defeating D1).
**Consequence:** `tests/test_read_paper.py`'s "no combination can reconstruct
the paper" invariant is replaced with: page-range bounding is honored, the
token budget is enforced, at least one span always returns even if it alone
exceeds the budget. #23/#30 must implement the per-answer ≤3-quotes-per-paper
gate (checkpoint Note A) — it no longer exists anywhere once this PR lands.
Spec updated: §6c (clarifying note: `read_paper`/row 1 is the model-read path,
not the row-4 enforcement point).

## 2026-07-06 — Per-worker git worktrees + Opus slice-boundary coherence auditor (owner directive)

**Context:** two problems surfaced landing #22. (1) Coordinator and workers
shared one git checkout, so the implementor's `git checkout -b` moved the branch
under the coordinator, and a coordinator harness commit landed on the PR branch
locally (caught before it reached the PR). (2) Per-PR review — even a strong
model — only sees the diff, so cross-issue drift, cross-layer contract rot, and
emergent boundary gaps (e.g. two `read_paper` calls breaching §6c per-answer
while each call is legal) have no owner.
**Decision:** (1) **Per-worker git worktrees.** Each worker runs in its own
detached worktree `.worktrees/<role>` (gitignored); the coordinator stays on
`main` in the primary repo and never git-collides with workers. Coordination
state (run-files, task logs) and the session jsonl are addressed absolutely /
by uuid, so a worker's worktree cwd doesn't hide them. `agent-spawn.sh` gained
`AGENT_BASE` (worktree ref) and `AGENT_MODEL`. (2) **Opus `auditor` role** runs
at each slice/epic boundary and before load-bearing issues, reads the whole
slice + spec + decisions + prior checkpoint, and writes
`docs/checkpoints/<date>-<slice>.md` (`COHERENT` / `NEEDS-WORK`, the latter
gating the next slice). Per-PR review stays Sonnet; load-bearing PRs (agent
loop, public API/SSE) get an added Opus review pass. Model tier is by blast
radius, not blanket — Sonnet demonstrably caught #57's single-opcode DoS, so
diff nuance is not the gap; whole-system coherence is.
**Alternatives rejected:** Opus on every PR review (burns limit for a
capability Sonnet shows); coordinator-commits-to-main-via-API only (divergence
bit us before); shared tree + discipline (just failed).
**Consequence:** `docs/sdlc.md` Worker harness section rewritten; auditor brief
added; `.worktrees/` gitignored; first checkpoint runs over the retrieval+tools
slice (#14/#16/#22) before #23.
Spec updated: no (process-only; the SDLC loop lives in `docs/sdlc.md`).

## 2026-07-06 — SDLC workers run as tmux-hosted claude CLIs for live observability (owner directive)

**Context:** the Agent/SendMessage subagent mechanism gave the coordinator no
live view into a running worker (edge-triggered "it finished" notifications
only) and gave the human no way to peek and catch a wrong action mid-flight;
subagents also lost re-messageability across a coordinator compaction (their
transcripts persist on disk, but the runtime handle does not cross the session
boundary). Observed twice while landing #16.
**Decision:** implementor/reviewer run as interactive `claude` CLIs in tiled
**panes of one `agents` window** in the human's **pre-existing** `rags` tmux
session (real name may be group-suffixed, e.g. `rags-0`), so every worker is
visible at once without switching windows. Four scripts under `scripts/`:
`agent-spawn.sh` (adds a titled pane per role, session-id pinned so the
coordinator knows the jsonl path, pane-id recorded so agent-send targets it;
fails loud if the session is absent — never creates it),
`agent-send.sh` (type + settle + Enter; short control messages only, big
context goes via files/PR), `agent-feed.sh` (human peek: one line per tool
call, MUTATE-flagged, read from the live-appended session jsonl — not scraped
from the TUI), `agent-pane.sh` (a worker opens a visible split pane for a
**long** run, teeing to `.claude/run/task-<label>.log`; short commands stay in
the worker's Bash). Machine channel = the on-disk jsonl; human channel = the
tmux window + feed. Compaction-by-respawn at task boundaries; durable context
stays in briefs + PRs + task files. Runs same-account (session limits are not
escaped, only made visible and cheap-to-resume); `ANTHROPIC_API_KEY` on the
workers is the escape hatch for true limit isolation, left unwired.
**Alternatives rejected:** headless `-p --output-format stream-json | tee`
(clean log but not human-watchable/steerable); scraping `tmux capture-pane`
(TUI grid is not a clean data channel); a second Claude subscription seat or
API-key billing now (cost, unjustified at this scale).
**Consequence:** briefs gained a working-surface rule (long→`agent-pane.sh`,
short→Bash); `docs/sdlc.md` gained a Worker harness section; `.claude/run/` is
gitignored runtime state.
Spec updated: no (process-only; the SDLC loop lives in `docs/sdlc.md`, not the
design spec).

## 2026-07-05 — Embeddings pivot to local-first: nomic-embed-text-v1.5 replaces Voyage as default (D5 second amendment, owner directive) (#13)

**Context:** the Voyage free tier turned out throttled to 3 RPM / 10K TPM for
no-payment-method accounts (previous entry below) — an 8.6h paced run for the
working corpus alone, and the same throughput cap would hit query-time in
production. The owner redirected: run embeddings **locally** by default,
keep Voyage working behind a flag for later.
**Decision:** `embedding_backend: Literal["local", "voyage"]` (default
`"local"`) in `config.py`; `make_backend()` is a literal two-branch dispatch
(§4d: no metaprogramming). Local backend is `sentence-transformers` running
**nomic-ai/nomic-embed-text-v1.5**, pinned to HF revision
`e9b6763023c676ca8431644204f50c2b100d9aab`, `truncate_dim=512`. Weights cache
under `corpus/models/` (gitignored — `.gitignore`'s existing `corpus/` rule
already covers it), never committed.
**Model choice, evaluated against the three stated criteria:**
(a) *Retrieval quality (English scientific text)*: nomic-embed-text-v1.5
publishes MTEB retrieval numbers including `ArxivClusteringP2P`/`S2S`
directly relevant to this corpus (HF model-index, checked 2026-07-05); no
sub-150M-parameter English-retrieval model found beats it on MTEB while also
meeting (b) and (c) below — checked against bge-small-en-v1.5 (33M, native
384 dims, no MRL to 512 — disqualified on (c)), gte-modernbert-base (149M,
~55.3 MTEB retrieval, no confirmed native 512-dim MRL), snowflake-arctic-
embed-m-v2.0 (305M, stronger retrieval but 2–3x the param budget), Qwen3-
Embedding-0.6B (600M) and jina-embeddings-v3 (570M) (both stronger but 4–5x
over budget), nomic-embed-text-v2-moe (475M total/305M active, multilingual-
focused — English BEIR ≈52.86, *lower* than v1.5's English MTEB). Models
that do beat v1.5 on raw retrieval are all 2–4x its parameter count, which
matters directly for (b).
(b) *Query-time CPU feasibility*: 137M parameters — the same model runs
query-time embedding inside the FastAPI process on the production VPS once
retrieval lands (#16), CPU-only, no GPU on that box. This is the load-bearing
argument for staying in the 30–120M-ish band rather than chasing raw MTEB
rank; ingest-time speed doesn't matter (Mac + MPS, one-time job) but
query-time speed on a small VPS does, every request.
(c) *512 dims via MRL*: the model card documents a trained (not just
truncated) Matryoshka checkpoint table — 768d: 62.28 MTEB, 512d: 61.96,
256d: 61.04, 128d: 59.34, 64d: 56.10 (huggingface.co/nomic-ai/nomic-embed-
text-v1.5, checked 2026-07-05) — 512 dims costs 0.32 points versus native
768, negligible. D5's 512-dim pin holds unchanged.
Nomic's asymmetric retrieval convention is mandatory, not optional: ingest
prepends `search_document: `, the query side (#16) MUST prepend
`search_query: ` or recall silently degrades — both prefixes are config
knobs (`embedding_doc_prefix`/`embedding_query_prefix`) read by both sides.
**Dependency gate — sentence-transformers==5.6.0** (measured 2026-07-05):
*Popular:* 18,878 GitHub stars (huggingface/sentence-transformers, via GitHub
API), 16.25M lifetime downloads of nomic-embed-text-v1.5 alone on the HF Hub.
*Maintained:* latest release 5.6.0 uploaded 2026-06-16 (PyPI), repo last
pushed 2026-07-03 (GitHub API) — Hugging Face org, human-reviewed merges.
*Security:* `pip-audit` (via `uvx pip-audit`, synced backend env) — no known
vulnerabilities; ships as wheels, no install-script surface; canonical HF
name, no typosquat risk. *Pinned:* `==5.6.0`. **PASS.**
**Dependency gate — torch==2.12.1** (measured 2026-07-05): *Popular:*
101,518 GitHub stars (pytorch/pytorch). *Maintained:* 2.12.1 uploaded
2026-06-17 (PyPI), repo pushed 2026-07-05 (GitHub API) — Meta/PyTorch
Foundation governance. *Security:* same `pip-audit` run, clean; wheel-only
install. *Pinned:* `==2.12.1`. **PASS.** (pypistats.org download-rank checks
were attempted but rate-limited (HTTP 429) on 2026-07-05; GitHub stars +
PyPI/HF metadata above are the substitute evidence — both packages are
unambiguously top-tier by any measure, so the gate holds despite the gap.)
*Alternatives rejected:* ONNX Runtime direct (skips sentence-transformers'
prompt/pooling/MRL-truncation handling — reimplementing that correctly for
one model is the kind of cleverness the gate exists to avoid); staying on
Voyage only and just fixing the pacing (doesn't solve the production
query-time throughput problem, which is the deeper reason for this pivot).
**Per-model artifact keying (the owner's core requirement for this pivot):**
every embedding artifact is now keyed by `embedding_model_slug` (short model
name + dims) so two models' vectors can never mix: `corpus/vectors/
<slug>.parquet`, shard dir `corpus/vectors/<slug>_shards/`, and the parquet
FILE METADATA additionally carries full provenance (model, revision, dims,
backend, created_at) via `EmbeddingProvenance`; `read_vectors()` refuses a
slug mismatch rather than silently reading another model's vectors. The
pre-existing Voyage partial shards moved under `voyage-4-lite_512_shards/`
under the same convention. Downstream: #14 keys Chroma collections by the
same slug; #18 tags eval runs by it — both issues carry matching coordinator
notes.
**Consequence:** the corpus embed run is now $0 (previously ~$0 net of the
Voyage free quota, but throttled); the tradeoff is CPU cost at query time
on the production VPS instead of an API call — untested until #16 lands and
is measured on real request latency. Voyage stays fully wired behind
`embedding_backend=voyage` for a future paid-tier or eval-driven swap; its
tests, pacing config, and DECISIONS.md history are unchanged.
**Revisit when:** a paid embeddings tier enters the budget (Tier-1 billing
addresses the throughput problem outright), or #18 evals show a paid/larger
model retrieves meaningfully better than nomic-v1.5 on this corpus, or #16's
measured query-time CPU latency on the target VPS spec is unacceptable (in
which case a smaller model, not a cloud API, is the first thing to try given
the throughput argument that motivated this pivot).
Spec updated: D5 (second amendment), §4b table (Embeddings + Vector archive
rows), §4c tree (`corpus/vectors/<model_slug>.parquet`).

---

## 2026-07-05 — Dependency gate: pyarrow==24.0.0 (vectors.parquet, D5) (#13)

**Context:** D4/D5 and the §4c tree name `corpus/vectors.parquet` as the
embedding archive, but §4b listed no parquet implementation; pyarrow entered
the lockfile in PR #53 without a gate record (review finding, coordinator-
approved contingent on this record).
**Gate record — pyarrow 24.0.0** (all numbers measured 2026-07-05):
*Popular:* 390,713,980 PyPI downloads last month (pypistats.org) — top-tier;
apache/arrow 16,904 GitHub stars. *Maintained:* 24.0.0 is the latest release,
uploaded 2026-04-21 (PyPI), Apache Arrow project (ASF governance,
human-reviewed merges). *Security:* `pip-audit` on the synced backend env —
no advisories against pyarrow; installs from binary wheels (the wheel format
has no install-script hook), canonical name from the Apache project, no
typosquat surface. *Pinned:* `==24.0.0`. **PASS.**
*Alternatives rejected:* fastparquet (a fraction of the adoption, no Arrow
interop); duckdb (a whole query engine for one read/write path); polars
(dataframe library where only the Arrow storage layer is needed).
*Side observation for the coordinator:* the same audit flags pre-existing
`chromadb 1.5.9` → PYSEC-2026-311 (no fix version published yet) — on main
before this PR, tracked outside it.
Spec updated: §4b table (Vector archive row).

---

## 2026-07-05 — Embeddings: Voyage AI free tier replaces OpenAI (owner directive 2026-07-05) (#13)

**Context:** D5 defaulted to OpenAI text-embedding-3-small @512d (~$2–13
one-time). The owner directed the pivot to Voyage AI, whose free tier grants
200M tokens per current-generation model. Verified against docs.voyageai.com
on 2026-07-05: `voyage-4-lite` is the cheapest current text model with
`output_dimension=512` support ($0.02/Mtok list, 200M free tokens, 1,000
inputs / 1M tokens per request; the documented 2,000 RPM / 16M TPM table is
Tier 1, which requires a payment method on file — see measured correction
below). voyage-3.5-lite — the model D5 originally named as the alternative —
is the same list price but gets **no** free quota as a superseded model.
**Decision:** embed with `voyage-4-lite` at 512 dims via raw httpx against
`POST /v1/embeddings` (httpx is §4b pre-approved; one endpoint does not
justify the `voyageai` package — the `openai` dep leaves the lockfile, this
was its only consumer). Corpus chunks send `input_type="document"`; the query
side (#15) must send `input_type="query"`.
**Frugality consequence:** while on the free tier, spend discipline is a hard
constraint: tests never call the API (faked backend + MockTransport), backoff
honors Retry-After and never retry-storms, `--estimate` (no key, no network)
prices every run first, and full runs need an explicit owner/coordinator go.
The working corpus (~4.5M cl100k tokens) and even the full corpus (~80–100M)
fit inside the 200M free quota, so the expected one-time cost is $0. Chunk
`n_tokens` remain cl100k_base counts — estimates and batch caps carry margin
because Voyage bills on its own tokenizer; billed truth is API-reported usage
(measured ratio on real chunks 2026-07-05: 1.009 Voyage per cl100k token).
**Measured correction (2026-07-05, first full run):** our no-payment-method
account gets **3 RPM / 10K TPM** (stated verbatim in Voyage's 429 body; the
docs publish no sub-Tier-1 numbers). Any batch over ~10k tokens can never
pass, which 429'd the first run's 100k-token batches permanently. Config
defaults now fit the unpaid tier: 9,000-token batches + 62s inter-batch pause
(`embed_batch_pause_seconds`) ≈ 8.7k tokens/min → the working corpus takes
~8.6 h, resumable throughout. Tier 1 (payment method added, still $0 via free
tokens) would cut this to minutes — the owner's call, not ours.
**Alternatives rejected:** staying on OpenAI (real dollars for no quality
argument yet); `voyageai` SDK (new dependency for one POST); voyage-3.5-lite
(no free quota).
**Revisit trigger:** Voyage free-tier terms change or quota exhausts;
milestone-2 evals (#19) show a better-retrieving model worth paying for; or
query-time latency/outage behavior forces a second provider.
Spec updated: D5 (amendment), §4b table (Embeddings row).

---

## 2026-07-05 — Live agent LLM: OpenRouter-routed model via env (owner directive)

**Context:** owner provisioned `OPENROUTER_API_KEY` + `OPENROUTER_MODEL`
(currently a DeepSeek "flash"-class reasoning model) in `backend/.env`,
replacing D3's Haiku-on-Anthropic-API plan for the live agent.
**Decision:** the live agent model is whatever `OPENROUTER_MODEL` names,
called through OpenRouter's OpenAI-compatible API. Known quirk to build
for (owner-reported, verify against provider docs when #22/#23 land):
reasoning/thinking-token models on OpenRouter require the reasoning blocks
from prior assistant turns to be passed BACK in subsequent requests during
tool-use loops, or tool calling degrades/fails. The hand-built loop (D2)
must persist and round-trip reasoning content per turn.
**Alternatives rejected:** staying on Haiku/Anthropic (owner chose
otherwise; revisit trigger unchanged — model swap is a config change).
**Consequence:** loop.py (#22/#23) is built provider-agnostic against the
OpenAI-compatible schema with reasoning round-trip support; D2/D3 spec
amendment lands in the same PR as that code. Cost model (§7) re-checked
then (DeepSeek pricing differs from Haiku).
Spec updated: pending — D2/D3 amended in the agent-loop PR (#22/#23).

---

## 2026-07-05 — Frontend scaffold: ESLint pinned to 9; CI gains pnpm/node actions (#26)

**Context:** scaffolding `frontend/` (Next 16 App Router, static export, React
19, Tailwind v4, TypeScript 6 — all §4b pre-approved and latest stable). Two
choices diverge from "just take latest" and need recording.
**Decision:** (1) **ESLint pinned to 9.x, not the latest 10.** ESLint 10.6
breaks an internal API (`scopeManager.addGlobals`) that eslint-config-next 16's
bundled typescript-eslint parser calls, so lint crashes under ESLint 10.
eslint-config-next 16's peer is `eslint >=9`; 9.x is its supported line and
Next 16's documented pairing. Latest-stable of the *compatible* line, not the
newest release. (2) **CI gains two SHA-pinned actions** for the frontend gate:
`pnpm/action-setup@b906aff` (v4, pnpm's own official action) and
`actions/setup-node@49933ea` (v4, first-party GitHub — grandfathered like
actions/checkout per the CI-actions gate). Both run `frontend-check`'s
lint/typecheck/test/typegen-drift in CI.
**Alternatives rejected:** ESLint 10 + overrides/patches (fighting a
bleeding-edge major the plugin ecosystem hasn't caught up to — churn for no
benefit); no CI frontend steps (frontend-check would silently pass without
Node/pnpm present).
**Revisit trigger:** bump ESLint to 10 once eslint-config-next declares
`eslint >=10` support and lint runs clean. `sharp`/`unrs-resolver` native
builds stay disabled (pnpm-workspace.yaml allowBuilds:false) — revisit only if
static export ever needs image optimization.
Spec updated: no (all packages are §4b pre-approved; this records version pins
+ CI-action gate records, not a stack change).

---

## 2026-07-05 — Budget gate is sequentially correct; concurrent overshoot accepted-and-bounded (#21)

**Context:** `budgets.check(session, ip)` is a pre-flight gate — it reads
current spend/counts from traces.py and returns Allow/Deny/Replay *before* a
turn runs. Real cost is known only after the LLM call and written by
`record_run()` afterward, so there is a check-then-record window. D11 does not
specify a concurrency model, and no request-serialization layer exists yet
(that lands with #23 loop / #30 chat route).
**Decision:** enforce SEQUENTIAL correctness now — the gate never Allows once
spend is at/over a cap, so no *sequence* of requests overshoots by more than
one request's cost. Accept the concurrent overshoot as bounded by
`(in-flight request count) × (per-message cost cap)` on top of the $0.50/day
global cap. This preserves D11's ~$15/mo ceiling intent, especially behind
Cloudflare rate-limiting; per-request cost is itself capped by the per-message
token budget, so the bound is small.
**Alternatives rejected:** pre-flight reservation (option 2) — cost is unknown
pre-flight, so it must estimate worst case, pessimistically denying legit
requests near the cap, and adds a reservation-reconciliation path for crashed
requests — speculative complexity for serving layers not yet designed.
App-level locking (option 3) — belongs in whatever runs the request (#23/#30),
not in this pure read-only gate.
**Revisit trigger:** tighten at #23 (loop) / #30 (chat route) with a
reserve-or-serialize step IF real abuse overshoots meaningfully. Money
comparisons use float (matches traces.db `cost_usd REAL` and D3 pricing
floats); sub-cent float drift is negligible against a $0.50 cap.
Spec updated: D11 (appended one sentence on the accepted-and-bounded
concurrent overshoot).

---

## 2026-07-05 — Chunk count is eval-gated, not a target; strict per-section packing ships (#12)

**Context:** strict-D7 chunking (each section packed into ~1k-token windows,
never crossing a section boundary) measured ~7,974 chunks over a real
200-paper extraction set — ~258k projected full-corpus, roughly 2x issue
#12's non-binding 80–120k estimate. 24% of chunks are <200 tokens (short
sections each become a chunk, plus a small tail window per section). One
paper produced 819 chunks — verified genuine (398-page monograph, 16 clean
headings), not a heading over-match.
**Decision:** chunk COUNT is not a spec target; it is eval-gated — D7's
revisit trigger is eval recall@k (D7/D14), not a count. Ship strict
per-section packing as-is. Add `chunk_min_tokens` (default 0 = disabled) to
config.py as the #19 eval-sweep knob; do not change chunking behavior now.
**Alternatives rejected:** tail-merge of sub-threshold chunks (opt 2) —
unmeasured recall risk: a short precise section (a key definition, a dataset
name) is exactly what hybrid retrieval should surface cleanly, and diluting
it into a neighbor could hurt recall; premature before #19 measures it.
Coalescing small adjacent sections (opt 3) — changes D7's "never cross
section boundaries" semantics without eval evidence.
**Consequence:** ~2x baseline chunk count accepted for the demo (embed cost
delta ~$1.5 one-time, <2 GB vectors — no budget concern); revisit at #19.
Spec updated: D7 (appended: count is eval-gated not count-targeted;
`chunk_min_tokens` merge knob exists disabled by default; revisit = #19).

---

## 2026-07-05 — Dependency gate covers CI actions; SHA pins mandatory

**Context:** reviewer questions on PR #45 — the gate said "before it enters
a lockfile", which GitHub Actions never do; the workflow tag-pinned
everything (`@v3`/`@v4`/`@v6`, mutable); and one PR cited a remembered
star count ("~1k") that measured 153.
**Decision:** (1) CI actions ARE dependencies (they run with the repo
token) and pass the same gate; (2) every action is pinned to a full commit
SHA with the version as a trailing comment — one rule including
first-party; (3) gate evidence carries measured, dated numbers.
**Gate record — extractions/setup-just (v3):** 153 GitHub stars (measured
2026-07-05), the installer casey/just's own README recommends, last push
2026-06-24, no install-script surface, no known advisories. PASS.
`taiki-e/install-action` considered (broader, heavier); apt install
rejected (~10x slower). actions/checkout v4 and astral-sh/setup-uv v6
grandfathered as gate-PASS (first-party GitHub / Astral, both already in
use since #10) — re-pinned to SHAs like everything else.
**Alternatives rejected:** SHA-pin third-party only (per-action judgment
calls; one rule is auditable); Dependabot-managed tags (mutable window
remains between releases).
**Consequence:** workflow files show SHAs; bumping an action version is a
deliberate diff. sdlc.md dependency gate amended in this PR.
Spec updated: no (process-only).

---

## 2026-07-05 — ty replaces pyright; tiered `just check` recipes (owner directive)

**Context:** the toolchain was uv + ruff + pyright; checks were scattered
(`be-test`, `be-lint`, CI steps hand-listed).
**Decision:** ty (Astral) is the backend type checker — one vendor for
env/lint/format/types, one speed profile. Check recipes are tiered:
`just backend-check` (ruff, format, ty, fast tests), `just frontend-check`
(pnpm lint + ts checks; graceful skip until #26), `just check` (both) —
and CI runs `just check`, so the local gate and the CI gate cannot drift.
Tracked as issue #44.
**Alternatives rejected:** keeping pyright (second vendor, slower, config
duplication); change-detection inside `just check` (git-diff-driven recipe
selection is cleverness the two side-specific recipes already cover).
**Consequence:** ty is newer than pyright — if it misses real type errors
pyright catches, or false-positives block work, that is the revisit
trigger (swap back is a two-line change since the gate is one recipe).
Spec updated: §4b table, §4c tree.


## 2026-07-05 — Idiomatic-by-default with autonomous deviation logging (owner directive)

**Context:** the review checklist covered hard constraints, correctness,
contract drift, and tests, but had no idiom dimension (Python, FastAPI,
React, state management, state machines).
**Decision:** binding per-path idiom rules live in `.claude/rules/`
(`python-backend.md`, `frontend.md`); implementor and reviewer briefs and
`docs/sdlc.md` wire to them. When idiomatic is unaffordable or hurts, the
implementor deviates and logs a DECISIONS.md entry (what, why, revisit
trigger) in the same PR — explicitly WITHOUT human sign-off; entries exist
for later revisiting, not gating.
**Alternatives rejected:** per-PR human approval of deviations (defeats the
autonomous loop); baking idiom into CLAUDE.md prose (bloats the always-on
contract; path-scoped rules load only where relevant).
**Consequence:** reviewer gains a priority-5 idiom dimension, severity by
blast radius; undocumented non-idiom is a finding, documented deviations
are judged against their own reasoning.
Spec updated: no (process-only).


## 2026-07-05 — Ops telemetry: OpenTelemetry + JSON logs from the start (owner directive)

**Context:** running agents were invisible; owner wants telemetry of every
kind available from day one, not bolted on when the demo is live.
**Decision:** OpenTelemetry initialized at every entrypoint from the start;
JSON-lines stdout is the default exporter, OTLP env-gated off;
`askrag/telemetry.py` is the single setup point; ops telemetry stays
separate from product traces.db. Tracked as issue #43.
**Alternatives rejected:** paid APM (cost cap, data leaves the box); plain
logging (no structure or trace correlation); reusing traces.db for ops
(product vs ops conflation).
**Consequence:** four pinned opentelemetry packages enter §4b pre-approved;
later issues attach spans to the documented naming convention instead of
inventing their own logging.
Spec updated: D15 (new), §4b table, §4c tree.


## 2026-07-04 — PR-loop SDLC adopted: coordinator / implementor / reviewer

**Context:** execution of the spec begins; agents need a repeatable flow.
**Decision:** one persistent implementor and one persistent reviewer agent,
coordinated by the main session; branch-per-issue PRs via `gh`; reviewer
findings judged (fix/reject) by the implementor; 3-round cap then
coordinator arbitration; coordinator is the only merger; Playwright
verification for user-visible work; dependency gate (popular + actively
maintained + advisory-clean) with entries logged here. Full protocol:
`docs/sdlc.md`; role briefs: `.claude/briefs/`.
**Alternatives rejected:** fresh implementor per task (loses accumulated
context); parallel implementors (merge conflicts + divergent conventions at
this project size).
**Consequence:** work is sequential by design; throughput trades for
context continuity. GitHub cannot record formal self-approvals, so the
reviewer's `VERDICT: GREEN` comment is the approval of record.
Spec updated: no (process-only).


## 2026-07-08 — Agent panel (#31): mockup reconciled to the shipped stream; citation-verification contract

**Context:** #31 builds the agent panel against the live `POST /api/chat`
SSE stream (#30). The `docs/mockup.html` agent demo predated every backend
contract and depicted flows the stream cannot produce: a `run_python` tool
(never built — the registry is 4 tools), raw model-authored SQL (removed in
#60), a `venue_rigor` corpus field (does not exist), and tool results
carrying chunk counts / similarity scores / row counts / sandbox internals
(the wire's `tool_result_summary` is name + ok/error only, §6c).

**Decision:**
1. The timeline renders exactly what the stream carries — tool name + args
   (from `tool_call`/`ui_action`) resolving to ok/error (from
   `tool_result_summary`). No result payloads, ever. `docs/mockup.html` was
   rewritten to match (friendly label → "done" tick, nothing more) and its
   fabricated tool / field / rail-facet flows removed.
2. Citation verification: a cited paper id becomes a clickable chip ONLY if
   it appeared in a `tool_call`/`ui_action` whose paired
   `tool_result_summary` was `ok=true` (the agent actually retrieved or
   navigated to it, reconciling the provisional call against its confirmed
   result per the `UiActionEvent` docstring). Otherwise the id renders as
   plain text. This is the anti-hallucination guard the #31 acceptance
   checklist requires and needs no change to the #30 stream.
3. SSE transport is `@microsoft/fetch-event-source` (already in §4b): native
   `EventSource` cannot POST a JSON body or read the `X-AskRAG-*` response
   headers the replay/session contract depends on.

**Alternatives rejected:** carrying retrieved ids/scores in the stream (§6c
surface widening for cosmetic timeline richness); verifying citations only
against `read_paper` (drops legitimate `drive_ui`-navigated ids); trusting
any model-written id (defeats the guard).

**Consequence:** the real timeline is leaner than the old mockup implied, by
design. If a future issue adds a stream event carrying retrieved ids (e.g.
for richer citations), revisit (2).

**Spec updated:** no — implementation contract for #31; §6c/§5 unchanged.

---

## 2026-08-28 — corpus.db carries planner stats, not a speculative index

**Context:** the cited-year histogram on the landing page joins every citation
edge (162,792 today) to `cited_works` to bucket it by the cited work's year. A
covering index `cited_works(arxiv_id, year)` was added with the schema on the
reasoning that it would make the join index-only. That reasoning was never
measured — the first attempt ran on a box saturated by an embedding job, and
the comment in `build_indexes.py` said so.

**Measured 2026-08-28** on a quiet box, against the real 162,792-edge graph,
median of 9 runs after a warm-up, on a throwaway copy of `corpus.db`:

| | median |
|---|---|
| with the index, no `ANALYZE` | 110.3 ms |
| without the index, no `ANALYZE` | 108.4 ms |
| with the index, after `ANALYZE` | 91.3 ms |
| without the index, after `ANALYZE` | 91.4 ms |

**Decision:** drop `cited_works_year`; run `ANALYZE` at the end of
`_write_corpus_db`.

Without statistics the planner ignores the index entirely — `EXPLAIN QUERY
PLAN` drives the join from `citations` and never names it, so the first two
rows are the same plan and differ only by noise. With statistics the planner
does choose it (`SCAN cited_works USING COVERING INDEX cited_works_year`) and
it still buys nothing: 91.3 against 91.4 ms. The entire 17% is the join order
`ANALYZE` unlocks, which is available without any extra index.

The snapshot is frozen (D12), so stats written at build time never drift —
this is the one situation where a one-shot `ANALYZE` is unambiguously correct.

**Alternatives rejected:** keeping the index "because it might help later"
(it is measured not to, and an unused index is build time, disk, and a false
signal to the next reader); `PRAGMA optimize` at connection time (the serving
connections are read-only, and a frozen snapshot needs stats computed once,
not re-derived per process).

**Consequence:** `/api/landing` measured at 270 ms end to end and
`/api/foundations/{id}` at 75 ms on the deploy-class box. If the cohort grows
by an order of magnitude, re-measure before assuming either still holds — and
re-measure any index before adding it back.

**Spec updated:** no — implementation detail below the D16 decision boundary.

---

## 2026-08-28 — the model-facing tool schema is not the security boundary

**Context:** the first live agent turn ever run against a real Messages API
failed twice on tool schemas, in ways no test could catch — every test scripts
the model client (house rule), so nothing offline ever posts `tools` to a real
endpoint.

1. `tools.1.custom.input_schema.type: Field required`
2. `input_schema does not support oneOf, allOf, or anyOf at the top level`

Both come from `query_metadata` and `drive_ui` being `RootModel`s over a
`Field(discriminator=...)` union, which pydantic emits as a top-level `oneOf`.

**Decision:** `ToolSpec.json_schema` flattens a top-level union into one object
schema — the union of every variant's properties, only the discriminator
required, its enum listing the permitted ops, and each optional property
labelled with the ops it belongs to.

The flattened schema is strictly looser than the union: it does not stop a
model from pairing `op="corpus_stats"` with `paper_id`. That is acceptable
because **the schema is what the model is told, not what is accepted**.
`dispatch` validates `raw_args` against `args_model` — the discriminated union
itself — so §5/§6 hold exactly as before: enum'd ops only, no model-authored
SQL, no URLs or HTML. Loosening the advertisement costs guidance, not safety.
Flattening the union in `args_model` WOULD be a security change, and is
therefore forbidden; `test_registry.py` asserts both tools keep their `oneOf`.

**Alternatives rejected:** nesting the union one level down (`{"request": {...}}`
is legal, since only TOP-level `oneOf` is refused) — it changes the argument
contract the model writes and the handler unwraps, to buy advertisement
precision that dispatch already enforces; hand-writing flat schemas per tool
(duplicates the args models, and drifts the first time a variant changes).

**Consequence:** a live turn is now the only thing that exercises the real
tool-schema shape. Re-run the smoke after ANY change to a tool's args model.

**Spec updated:** no — §5 tool contracts and §6 threat model are unchanged;
this is how the same contract is expressed on the wire.

---

## 2026-08-28 — what counts as a quote (§6c row 4's missing floor)

**Context:** issue #36 enforces §6c row 4 server-side at the answer boundary
(`askrag/api/answer_guard.py`). The rule fixes two numbers — ≤50 words per
quote, ≤3 quotes per paper per answer — but never defines the floor: how long a
verbatim run must be before it counts as one of the three.

The first implementation used a 6-word floor. On a live turn it removed NINE
quotes from a faithful Qwen3 answer, tripping on ordinary technical phrasing
("increasing the proportion of STEM, coding, reasoning") and leaving prose like
"High-quality long context training [quote removed: §6c per-paper limit]," with
specific composition: "[quote removed]". The guard was enforcing the letter of
the rule and destroying the product.

**Decision:** `config.quote_min_words = 15`, and elide with "[…]".

Verified against the real corpus and a real recorded answer (375 words, 5
papers, 76 chunks):

| floor | quotes dropped from a genuine answer |
|---|---|
| 6 | 3 |
| 10, 15, 20 | 0 — byte-identical to the model's own output |

And the cap still bites, against real chunk text:

| attack | outcome |
|---|---|
| 200/120/60-word verbatim dump | truncated to exactly 50 words |
| the same dump uppercased and re-wrapped | truncated — normalization defeats laundering |
| 40-word quote | passes, correctly: it is under the 50-word cap |
| paraphrase | untouched |

**Alternatives rejected:** keeping the 6-word floor (spec-literal, but it makes
faithful answers incoherent, and a guard that mangles real output gets switched
off — the worst possible end state for a §6 control); capping total verbatim
VOLUME per paper instead of counting quotes (defensible, arguably better, but
it is not what row 4 says and inventing a different rule needs its own
decision); a bracketed policy sentence as the elision marker (it was the actual
cause of the incoherence, and an audit reads the log, not the paragraph).

**Consequence:** the floor is a tunable, so tightening it is a config change,
not a rewrite. If quoting behavior changes materially — a different model, or a
prompt that encourages heavy quoting — re-measure against a real answer before
trusting the number.

**Spec updated:** yes — §6c gains a 2026-08-28 clarification defining the floor
and the elision marker.

---

## 2026-09-14 — the reader opens any paper we can name, not only indexed ones

**Context:** a foundation's detail view lists two kinds of paper. Indexed
citers opened in our own reader (`/app?paper=`); co-cited works — Llama 3,
VGG, layer norm — were sent off to arxiv.org, because the viewer could only
render a paper the corpus held a row for. Both are papers, both sit in
identically-framed panels a hand's width apart, and nothing on screen
explained why one opened here and the other left the site. Measured on the
deployed corpus: all 40 foundations are indexed (they are the frontier
manifest), but 28 of the 70 co-cited works shown across them are not.

**Decision:** the viewer resolves an arxiv id against `GET /api/papers/{id}`
first and `GET /api/foundations/{id}` second (`hooks/use-viewer-paper.ts`),
and every paper on the landing surface opens in it. Reading is not a second
destination: the detail view mounts with the foundation already open beside
its citation panels (`components/landing/paper-reader-panel.tsx`, same
`arxiv-pdf-frame.tsx` as the app shell), and clicking any paper in either
list swaps the reader to it without leaving the page.

This is not a D16 widening. D16 forbids surfacing a paper the app cannot
retrieve, and nothing here changes retrieval: `scope_paper_ids`,
`INDEXED_PREDICATE`, the explorer's lists and the agent's tools are untouched.
What the reader gets is the PDF, and §6b already routes those bytes from
arxiv.org to their browser, version-pinned, never through us — `arxiv-pdf-
frame.tsx` needs the id and the version and nothing else. The version comes
from `cited_works.version`, so a fallback-resolved paper is pinned exactly as
a corpus one is.

The difference the reader cannot see is that the agent has no text for such a
paper, so the excerpts pane says so instead of offering "ask the agent about
this paper" — an offer that would return nothing, now or ever. `indexed` is
derived from WHICH of our records answered, never read off a response field:
no `readable` flag reaches the wire, which is the part of D16's posture this
change had to keep.

**Alternatives rejected:** restricting `_co_cited` to indexed works (it would
turn a claim about the literature into a claim about our index — those works
really are cited alongside these papers, whether or not we hold them); a
`readable` flag on the wire so the UI could sort papers into ours and theirs
on screen (the two-tier UI D16 exists to avoid).

**Consequence:** `/api/foundations/{id}` now serves viewer metadata for any
cited work, not only one high enough in the ranking to be a card. If that
route is ever narrowed to the top N, the viewer's fallback narrows with it and
those papers go back to erroring.

**Spec updated:** no — §6b already requires this PDF path, and D16's retrieval
scope is unchanged.

---

## 2026-09-30 — the agent panel follows the theme (owner directive)

**Context:** the 2026-08-13 theming entry kept the machine-room palette fixed
dark in both themes, as the claim that the agent half is instrumentation. In
light mode that put a black column beside a pale page, and the owner asked for
the panel to follow the theme.

**Decision:** the agent panel's tokens (`--machine*`) move into `:root` /
`.dark` like the rest of the palette. Light is a near-white column a step off
the rail's `--panel`; dark keeps the original machine-room values. Its accent,
amber and rust become text tokens of their own (`--machine-accent`,
`--machine-amber`, `--machine-rust`), because the shared fills of those names
read 3.0:1 or less on the light surface.

The PDF surround stays dark in both themes, since the page it frames is always
white. It stops borrowing the agent tokens and gets fixed `--color-surround*`
tokens instead, which only worked before because both surfaces were fixed.

**Guard:** `tests/globals-css.test.ts` measures every text/surface pair in
both themes against WCAG AA, and fails on a hard-coded hex colour in a
component, which would bypass the table.

**Revisit when:** a surface needs to differ per theme inside the agent panel
beyond what the tokens express, or the owner wants the dark instrument column
back as a deliberate contrast.

**Spec updated:** no. The spec does not fix the agent panel's palette; this
reverses the 2026-08-13 entry's bullet only.

---

## 2026-09-30 — the golden set is model-checked, not hand-verified (owner directive)

**Context:** #17 required a human pass over every candidate before it
counted, and that pass never happened, so D7's chunking and D8's rerank
decisions still ship as guesses and the benchmarks page has no scores. The
owner directed that the set be built without any human step.

**Decision:** D14 is amended (2026-09-30): GLM 5.3 Flash drafts, Muse Spark 1.3
contributor checks (the owner's pick; the account guardrail blocks the
Anthropic, Google and OpenAI slugs), and a record counts when it passes the deterministic checks and the
checker's grounded / answer-correct / not-closed-book verdicts. `verified`
is replaced by a `checks` object on each record. #17 is superseded.

**Consequence:** every number from this set is labelled model-checked. The
risk is shared blind spots between two models; the different-family checker
and the verbatim-span rule are the mitigations.

**Revisit when:** a spot check of twenty records finds more than two wrong,
or two configurations land within five points on a decision that matters.

**Spec updated:** yes, D14 amendment (2026-09-30).

## 2026-10-01 — the golden set gains a vocabulary-mismatch type (owner directive)

**Context:** the first retrieval eval (#18) scored BM25 at 97% recall@5 on
single_hop questions, so the set could not show where semantic search helps,
which the benchmarks page exists to show.

**Decision:** a `vocabulary_mismatch` type: questions in the searcher's own
words for a need the paper names in its terms, barred from every chunk word in
at most 500 chunks, and counted only when the checker also finds the question
natural (not a roundabout rewording of a known term).

**Consequence:** on 22 counted questions, recall@5 is BM25 36%, vector 73%,
hybrid 77%. BM25 still matches on common field words the rule allows; the bar
was not tightened further, because that trades natural questions for a lower
keyword score.

**Revisit when:** BM25 recall@5 on the type reaches the vector leg's, or a spot
check finds more than two in ten counted questions unnatural.

**Spec updated:** yes, D14 amendment (2026-10-01).

## 2026-10-02 — D17 withdrawn: PDFs are kept (owner directive)

**Context:** collecting September 2026 (12,520 cs papers, 50.6 GB on the
mirror) does not fit the 38 GB free on the corpus volume. D17 said PDFs are
deleted after extraction, but no code ever deleted them; `corpus/pdfs/` holds
154 GB.

**Decision:** D17 is withdrawn. PDFs fetched from the GCS mirror are retained.
D19's card images render from them, and re-extraction runs over local bytes.

**Consequence:** disk bounds the corpus, about 50 GB per month of cs. The
September pull needs space found first (volume growth or cleanup elsewhere).
§6b is untouched: nothing serves, proxies or caches a PDF outward.

**Revisit when:** the volume cannot grow to hold the months the landing page
needs.

**Spec updated:** yes, D17 replaced by a withdrawal note (number kept).

## 2026-10-02 — Explore is the home page; the overview becomes Citations (owner directive)

**Context:** `/` opened on the citation dashboard, and the whole catalog sat
one click away at `/papers`. The dashboard's hero also carried the share of
each cohort month we hold, which scopes the catalog more than the ranking.

**Decision:** `/` is Explore (the catalog filter), the dashboard moves to
`/citations` under the name Citations, and the rail lists Explore, Citations,
RAG demo. The per-month share moves to Explore's top bar as a compact meter.
`/api/coverage` gains `cohort` (the id-months `cohort_months` selects), so the
client picks the months without re-deriving the threshold. `/papers` is
removed without a redirect.

**Consequence:** a visitor lands on papers, not on a claim; the agent is still
entered from a claim on Citations. Old `/papers` links 404.

**Revisit when:** the site goes public and `/papers` links exist outside the
tailnet (then add one Caddy redirect), or visitors are found not to reach
Citations from the rail.

**Spec updated:** yes, §4c decision 2 amendment (2026-10-02), and the
2026-09-13 home-as-dashboard amendment marked superseded.

## 2026-10-02 — Trends tab for the category census; "Just indexed" deleted (owner directive)

**Context:** Citations carried two panels that are not about citations: a
list of the newest indexed papers, which Explore sorted by newest already
shows, and the category census, which counts what arXiv posted rather than
what we hold.

**Decision:** the census moves to a new static route `/trends` (rail tab
"Trends"). The newest-papers list is deleted with its endpoint
`GET /api/latest`. Citations is now the ranking, uptake beside citation age,
and the method note. Citations and Trends share one `DashboardShell`.

**Consequence:** Citations shows only citation counts. A visitor wanting new
papers uses Explore.

**Revisit when:** Trends gains a second panel that is not a census (then
reconsider its name), or the newest-indexed list is needed somewhere Explore
cannot serve it.

**Spec updated:** yes, §4c decision 2 amendment (2026-10-02) extended, and
the repo layout's routes_landing.py line.

## 2026-10-04 — golden questions are short search queries (owner directive)

**Context:** the golden set averaged 35 words per question, written like
prompts ("In the event-forecasting model's ablation that removes its time
gate, by how many percentage points..."). Researchers type short queries, so
the benchmark measured retrieval on input it will never see.

**Decision:** every question is at most 12 words (`golden_question_max_words`),
culled deterministically past that; the checker rules on naturalness for every
type; table questions ask for a trend or comparison, not a cell; known_hard and
multi_hop quotas rose to 45 and 35 because short versions of them cull hard.

**Consequence:** 102 of 213 count, mean 9.6 words. Recall@5: BM25 64%, vector
63%, hybrid 71%. The vocabulary_mismatch gap (36% vs 73% before) shrank to 48%
vs 52%, within noise; the benchmarks page's finding moved from "semantic wins
when the asker lacks the paper's words" to "neither wins alone; fusion does".

**Revisit when:** a spot check finds counted queries that still read as written
from the paper, or any type falls under ten counted questions.

**Spec updated:** yes, D14 amendment (2026-10-04).

## 2026-10-05 — retrieval evals score the top 10 the agent reads (owner directive)

**Context:** the benchmark reported recall@5 and @20 over a fusion of each
leg's top 20, but the agent reads the top `search_top_k` (10) fused from each
leg's top 10, so no reported number described what ships. Practice for RAG
retrieval benchmarks is recall at the k the application uses, with nDCG@10 as
the ranking metric BEIR and MTEB report.

**Decision:** one cutoff, k = `search_top_k`, for depth and every metric;
nDCG@k and median latency added; `eval_recall_ks` deleted; README rows ranked
by recall@k. The benchmarks page leads with that ranked table and 95%
bootstrap intervals, puts recall per query type beside it, and folds
examples, every query's ranks and the method into closed disclosures.

**Consequence:** recall@10 hybrid 80% (72-87%), BM25 79%, vector 73%; the
intervals overlap, which the page states instead of a headline sentence.

**Revisit when:** `search_top_k` changes (rerun at the new k), or the set grows
enough that the intervals separate.

**Spec updated:** yes, D14 amendment (2026-10-05).


## 2026-10-05 — the OpenRouter guardrail dropped DeepSeek and GLM; models move (owner directive)

**Context:** the account's OpenRouter allowlist now holds Muse Spark 1.3
Contributor, Space Bunny Alpha, gpt-oss-120b and the embedding model, plus
MiMo V2.6 Flash on the owner's pick. DeepSeek V4 Flash (the tailnet agent) and
GLM 5.3 Flash (the golden drafter) both return 404 behind the guardrail, so
the deployed agent could no longer answer.

**Decision:** `smoke_model` is `xiaomi/mimo-v2.6-flash` ($0.14/$0.28 per
million tokens, tool calls verified; one live chat answered with six searches
for $0.0067). The golden drafter is `stealth/space-bunny-alpha`; the checker
stays Muse Spark. gpt-oss-120b was tried as drafter and lost (54 counted of
197, against 83 for Space Bunny). A stealth model is not used for the agent:
it can be withdrawn without notice, which is the failure that prompted this.

**Revisit when:** the allowlist changes again, or Space Bunny leaves
OpenRouter before the next redraft.

**Spec updated:** yes, D14 amendment (2026-10-05) for the drafter; the smoke
model is not a spec decision (D3's prod agent is unchanged).

## 2026-10-05 — golden set: ambiguity check, related multi-hop pairs, checkpointed redrafts (owner directive)

**Context:** a counted question's expected answer was wrong as typed (CNF
clauses answered as if Horn); multi-hop drafts failed `natural` 16 of 21 as
two stapled questions; and three interrupted redrafts lost all their work
because the drafter wrote only at the end.

**Decision:** an `unambiguous` checker verdict, backfilled onto the committed
GLM-drafted set rather than redrafting it (93 count, from 102); multi-hop
pairs are body sections sharing at least three rare terms; each checked record
is checkpointed; the checker's token cap rises from 3,000 to 6,000 (9 of 219
replies came back empty or cut); a reply with no usage block fails one draft
instead of the run.

**Consequence:** the backfilled verdicts came from a one-verdict prompt with
the grader's own wording, not the full grading call; the next full redraft
grades them together. Related pairs lifted Space Bunny's multi-hop yield from
4 to 6 of about 30: most drafts still join two questions with "and", so the
type's brief is the next suspect.

**Revisit when:** the next full redraft, or multi-hop stays under ten counted.

**Spec updated:** yes, D14 amendment (2026-10-05).

## 2026-10-05 — the eval measures the reranking ceiling and one query rewrite (owner directive)

**Context:** the next question is which primitive does the agent's work:
reordering what search already found (a reranker) or changing the query
(rewriting). Neither had a number.

**Decision:** every row reports recall@50 beside recall@10, and a fourth row
scores hybrid over one rewrite of each question by `smoke_model`, generated
by `just rewrites` into a committed file and refused when stale.

**Consequence:** run `b9a4726765fe`: hybrid recall@10 79%, recall@50 93%
(a 14-point ceiling for any reranker of the top 50); rewrite + hybrid 65%,
3 questions helped and 18 hurt. A reranker remains worth measuring; replacing
the query with one rewrite is not.

**Revisit when:** a reranker is built (score it against the 93% ceiling), or
the rewrite is fused with the original query instead of replacing it.

**Spec updated:** yes, D14 amendment and a D8 note (2026-10-05).

## 2026-10-05 — the rerank stage is a local cross-encoder; measured, not enabled (owner directive)

**Context:** the eval put hybrid at 79% recall@10 and 93% recall@50, so a
reranker of the top 50 could add at most 14 points. D8 named Voyage rerank or
an LLM listwise pass as candidates.

**Decision:** a local cross-encoder through `sentence-transformers` (already a
dependency, $0): Alibaba-NLP/gte-reranker-modernbert-base, Apache-2.0, pinned
to revision f7481e6, reading whole chunks (1,280 tokens). The eval scores it
as "Hybrid + rerank". cross-encoder/ms-marco-MiniLM-L6-v2 was also run as a
fast baseline and is not kept.

**Consequence:** recall@10 87% (from 79%), nDCG@10 0.71 (from 0.58); MiniLM
scored 72%. On this shared 4-core host the model needs about 153 s per
question, so `just eval` now runs about 4.5 hours and must run detached, and
`rerank_enabled` stays False.

**Revisit when:** a hosted reranker or GPU makes per-query latency
sub-second (then measure it against this row), or the set grows enough to
put intervals on the 8-point gain.

**Spec updated:** yes, D8 amendment (2026-10-05).

## 2026-10-05 — hosted reranking through OpenRouter, and cost per query in the evals (owner directive)

**Context:** the local cross-encoder lifted recall@10 from 79% to 87% but
took about 153 s per query on the build host. OpenRouter lists nine rerankers
(Voyage, Cohere, Qwen, NVIDIA), all blocked by the account guardrail until
the owner allowlisted voyageai/rerank-3-lite.

**Decision:** `rerank_backend` chooses `openrouter` (default, Voyage
rerank-3-lite) or `local`. Cost is taken from each provider reply
(`usage.cost`) for the embedding, the rerank and the rewrite, recorded per
question in the run store, and shown as mean cost per query in every row.
Rate limits and 5xx retry with exponential backoff (6 attempts from 2 s).

**Consequence:** run bf072fb0bfba: Voyage rerank 90% recall@10, nDCG@10
0.79, 0.74 s and $0.00066 per query, ahead of the local model's 87%; a full
eval takes about 3 minutes instead of 4.5 hours. The rewrites were
regenerated to carry their cost, which moved the rewrite row from 65% to
68% (MiMo is not deterministic).

**Revisit when:** the reranker is wired into search_corpus (measure answer
quality and turn cost with it), or a cheaper allowlisted reranker appears.

**Spec updated:** yes, D8 amendment (2026-10-05).
