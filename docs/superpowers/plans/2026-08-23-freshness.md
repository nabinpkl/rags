# Freshness — how new papers reach the corpus, measured

Status: **proposal**, 2026-08-23. Companion to `2026-08-23-corpus-pulse.md`
(the dashboard that *shows* freshness); this one is the pipeline that
*produces* it. Becomes issues once the owner picks from §6.

## 1. What we measured (Oracle host, 4× Neoverse-N1, 23 GB, 2026-08-23)

| Stage | Measured | Full corpus (6,460 papers, ~260k chunks) | 300-paper month (~12k chunks) |
|---|---|---|---|
| OAI-PMH harvest | 1,000 records/page, 3 s pacing (§6b) | — | ~23 pages ≈ 2 min for all of `cs` |
| PDF download, arXiv scraper | 3 s + jitter per PDF (§6b) | — | ~20 min, ~1.1 GB |
| PDF download, **Google mirror** | unthrottled, 8 parallel, version-pinned | — | **1–2 min**, ~1.1 GB |
| Extraction (PyMuPDF4LLM) | 11.9 s/paper, one core | **5.3 h** on 4 workers | 15 min |
| Embedding, local nomic, **this CPU, float32** | **0.38 chunks/s** | **188 h** | **9 h** |
| Embedding, local nomic, **fp16 on this CPU** | did not finish 96 chunks in 500 s | unusable | unusable |
| Embedding, Mac GPU (mps, fp16) | 3.6 chunks/s (`embed_run_local_fp16_20260705.log`) | 20 h | 55 min |
| `build_indexes` (drop-and-rebuild, SQLite + Chroma) | not measured; sub-hour expected | ~ | ~ |
| `deploy-reseed` | compose down/up + chroma volume copy | ~1 min downtime | ~1 min |

arXiv volume (Kaggle seed, 2026): **`cs` adds 12.6k–23.1k papers/month;
cs.CL alone 1.5k–2.6k.** A bare `just update` (set=cs, no cap) would attempt
every one of them: ~19 h of paced downloads, ~40 GB, ~900k chunks — per
month. It is not a freshness job as written; it is a firehose with a
watermark.

**The Google mirror (`gs://arxiv-dataset`, measured 2026-08-23 04:48 UTC):**

| month | papers | objects (all versions) | size | avg PDF |
|---|---|---|---|---|
| 2512 | 25,070 | 36,409 | 145 GB | 4.1 MB |
| 2601 | 23,277 | 33,369 | 121 GB | 3.7 MB |
| 2602 | 24,288 | 34,550 | 139 GB | 4.1 MB |
| 2603 | 30,040 | 40,596 | 166 GB | 4.2 MB |
| 2604 | 28,193 | 36,510 | 135 GB | 3.8 MB |
| 2605 | 31,602 | 39,541 | 150 GB | 3.9 MB |
| 2606 | 32,036 | 38,172 | 141 GB | 3.8 MB |
| 2607 | 29,681 | 33,901 | 113 GB | 3.4 MB |
| 2608 | 13,559 so far | 14,425 | 46 GB | 3.2 MB |

That is all of arXiv (233 month folders, 0704 → 2608); `cs` is ~40–45 % of
it by the Kaggle counts, so ~12–23k papers and ~50–70 GB a month. The
mirror syncs in **batches on Sundays, every one to two weeks** (2607 landed
on Jul 12, Jul 26, Aug 9, Aug 16; 2608 on Aug 9, Aug 16), so it trails
arXiv by **~1 week right after a sync, up to ~2 weeks before the next**.
On Aug 23 the newest paper in it is 2608.13561 (submitted ~Aug 14).
Downloads from it are unthrottled and parallel (§6b pacing applies to
export.arxiv.org, not to Google's bucket): 300 PDFs ≈ 1.1 GB ≈ **1–2 min at
8 connections**, versus ~20 min through the paced scraper. The listing
also returns each id's versions and sizes, which is how the delta gets
version pins without a second arXiv call.

Consequences: the delta pulls PDFs from the mirror, not the scraper; the
monthly run targets the *previous* month and is scheduled for the second
Sunday after month-end, when the mirror has the whole month; and disk per
month is ~1.1 GB for 300 papers, not the 0.6 GB estimated from the
current corpus (recent PDFs are bigger).

Pipeline properties that help (all verified in code):

- Extraction is incremental (skips when the JSON is newer than the PDF;
  `extract_pdfs.py:211`), embedding is resumable by `chunk_id` with shard
  merge (`embed_chunks.py:372,487`), chunking rewrites `chunks.jsonl` from
  all extractions in seconds. So a delta only pays for *new* PDFs.
- `build_indexes` is drop-and-rebuild by design (D4: the pair can't drift).
  It writes `corpus.db` to a tmp file and renames; Chroma is recreated. One
  batched `export.arxiv.org` call backfills versions for OAI-harvested
  papers (they arrive versionless — `arxiv_ingest.py:343`), so D9 pinning
  survives a refresh.
- Licenses come from the Kaggle seed at build time; OAI papers get `NULL`
  → the conservative §6c caps. (The OAI `arXiv` format does carry
  `<license>`; parsing it is a five-line follow-up, not a blocker.)
- New papers get no diversity facets (authority/rigor are computed by
  `just diverse` from the seed + the frozen citation file). The rigor
  column is data-gated per row already; the agent's `paper_facets` reports
  nulls honestly.

The host now has the room: the corpus sits on a 500 GB volume
(`/mnt/data/askrag`, 475 GB free), so a decade of ~1.1 GB/month deltas and
several parallel snapshots fit.

## 2. The shape: a sampled monthly delta, built beside prod, swapped atomically

**The delta is a sample, by the same logic the corpus is a sample.** The
current "recent" slice is `just latest` — cs.CL-primary, newest-first, to a
4 GB budget. The monthly delta continues exactly that series:

> Each month, harvest all `cs` metadata since the watermark (CC0, 2 min),
> keep cs.CL-primary records, pick **N = 300** spread evenly across the
> month's submission days (deterministic: sorted by `published`, every
> k-th), download those PDFs **from the Google mirror** (version-pinned,
> unthrottled), and ingest only them.

300/month ≈ 12–20 % of cs.CL's output, 3.6k papers/yr, ~145k chunks/yr.
The explorer's "newest" is then never older than the refresh, and the
sampling rule is one sentence a visitor can be told.

**Snapshots are directories, not files.** `/mnt/data/askrag/snapshots/
<YYYY-MM>/{corpus.db, chroma/}` built by the job; `/mnt/data/askrag/corpus`
(what compose mounts, via `ASKRAG_CORPUS_HOST_DIR`) gains a `current` →
`snapshots/<YYYY-MM>` symlink that the swap step flips after the build
validates. Serving never sees a half-written DB (D4's read-only posture is
untouched: the API still opens `mode=ro`; the job writes somewhere the API
isn't looking). Rollback = flip the symlink back + reseed. Keep the last
two.

**Collector change (the only new code of substance):** `update` gains
`--category-prefix`, `--per-month N` and a `--spread` selector (harvest
everything in the window first, then choose; today it downloads in OAI
order and stops at `--limit`, which is "the first N" not "N across the
month"). Everything downstream is the existing chain.

**One recipe:** `just refresh` =
`update --category-prefix cs.CL --per-month 300` → `extract` → `chunk` →
`embed` → `build-indexes --out snapshots/<month>` → validate (counts,
`INDEXED_PREDICATE` total ≥ previous, spot-query) → flip `current` →
`deploy-reseed` → `digest` (pulse plan, Phase 2). Each stage resumable;
rerunning a failed refresh picks up where it stopped.

## 3. Where each stage runs — the embedding question

Everything except embedding is cheap on the VPS. Embedding has three
options; they differ by an order of magnitude and by who has to be awake.

| Option | Monthly delta (12k chunks) | One-time full ingest (#15, 260k chunks) | Ops | Cost |
|---|---|---|---|---|
| **A. VPS CPU, `nice -n 19`, overnight** | **9 h**, unattended | 188 h ≈ 8 days, unattended (query embedding shares the CPU — `nice` keeps the API responsive) | none after setup | $0 |
| **B. Mac GPU** (today's D12 flow) | 55 min, but a human runs it | 20 h in resumable overnight shards (proven path; shards merge) | monthly chore, ~30 min hands-on | $0 |
| **C. Rented GPU for the bulk, then A** | 9 h on VPS | ~1 h on a T4/A10-class box | one afternoon, once | ~$1–3 one-time (§7 "one-time" row) |

Only the *model* must be identical across bulk and delta (one Chroma
collection per model slug, `read_vectors` refuses another model's parquet).
Where it runs is free to vary: B and C produce the same `nomic-embed-text-
v1.5_512` parquet as A. Voyage (`embedding_backend=voyage`) is *not* a mix-in
— it is a different model, so it would mean re-embedding everything *and*
pointing query-time at Voyage; rejected here as a freshness tool (it's a D5
decision, not a cadence one).

Data movement for B/C is small: the VPS extracts and chunks (5 h, CPU),
ships `chunks.jsonl` (~500 MB for the full corpus, ~25 MB/month) out, and
gets the parquet back (~530 MB full, ~25 MB/month). PDFs never leave the
volume.

**Recommendation:** **C for the one-time bulk, A for the monthly delta.**
A alone is honest but makes #15 an 8-day background job; B keeps a human
in the monthly loop forever, which is what D12 already is and what the
user wants out of. C+A is one afternoon, then zero-touch.

If A is chosen for the delta, two cheap speedups are worth one experiment
each before accepting 9 h: `embed_local_dtype=float32` on CPU is already
~∞× faster than fp16 here (needs a config note: fp16 is a GPU setting);
`embed_encode_batch_size` and an explicit `torch.set_num_threads(4)` may
move 0.38 → 0.6–0.8 chunks/s. ONNX/int8 export would likely give 2–3×, at
the cost of a new dependency — not in this plan.

## 4. Cadence and trigger

- **Monthly**, the second Sunday after month-end (when the mirror has the
  whole month — §1), via a **host `systemd` timer** running `just
  refresh` as `ubuntu` with `nice`, logging to `/mnt/data/askrag/logs/
  refresh-<month>.log`. Not cron-in-a-container, not a service in compose:
  the job needs the host's `docker` (for reseed) and the volume; the API
  never runs ingest code (D12's point survives intact).
- **Failure is visible, not silent**: the pulse band shows "snapshot
  2026-09 · N days old" — a missed month reads as a stale date on the
  front page. The timer unit also writes a one-line status file the
  README tells you to check. No alerting stack.
- **D12 amendment** (same PR): "refreshing prod = monthly sampled delta,
  built by a host timer into a fresh snapshot directory and swapped
  atomically; the serving process still never ingests." *Rejected* keeps
  "cron on the VPS that writes into the served DB" (that is the D4 hazard
  the original text meant) and "event-driven refresh". Revisit trigger:
  a timer run fails two months in a row, or the delta wants to grow past
  what a night of CPU embeds (~400 papers).
- §6b item 7 is respected by construction: the collector's pacing is
  unchanged, and the OAI harvest is 23 requests a month.

## 5. Costs

| Item | |
|---|---|
| Disk | +1.1 GB PDFs + ~60 MB index per month; two snapshots live at once (~2× index) |
| CPU | one night a month (A) |
| Money | $0 recurring; ~$1–3 once (C) |
| Downtime | ~1 min at reseed, monthly |
| Human | 0 after setup (A/C); 30 min/month (B) |

## 6. Decisions for the owner

1. **Embedding placement** — C+A (recommended), A only, or B. Blocks #15
   and the cadence.
2. **N and the category rule** — 300 cs.CL-primary/month by even spread
   (recommended), or a broader `cs.*` mix (then N per category).
3. **Timer vs manual** — host systemd timer (recommended, needs the D12
   amendment) vs keep D12's manual flow with the new `just refresh` recipe.
4. **Parse OAI `<license>`** in the same change (recommended; cheap) or
   leave new papers on the conservative default.

## 7. Issues this becomes (after §6)

1. collector: `update --category-prefix/--per-month/--spread` + license
   parsing + tests
2. backend: `build_indexes --out <snapshot dir>`, snapshot `current`
   symlink convention, `just refresh` recipe, validation step
3. deploy: `ASKRAG_CORPUS_HOST_DIR` → `…/corpus/current`; README
   "Refreshing the corpus" rewritten; systemd timer + unit files under
   `deploy/host/`
4. spec: D12 amendment + DECISIONS.md entry; config note that
   `embed_local_dtype=float16` is a GPU setting
5. #15 executed per the chosen placement; report committed
