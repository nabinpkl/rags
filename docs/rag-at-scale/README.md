# RAG at scale notes

Source material for a Documentation page on what limits RAG beyond the
vector store: corpus size, document type, and the graph, visual and cache
variants. Each entry says what happens, what decides it, where it bites,
and what it means for askRAG today. Store-specific questions live in
`docs/vector-db/README.md`; add here when a RAG question gets researched.

Numbers come from the linked sources unless marked *computed* (arithmetic
on this repo's figures) or *measured*.

## Corpus size

### What happens

Past a certain size, the vector store is rarely what limits retrieval; the
corpus is. Exact nearest neighbours stop being the right passages:

- **Dilution.** As the corpus gets broader, dense retrieval separates
  documents less well, even when the index returns the true nearest
  neighbours. One deployment fell from 75% to under 40% accuracy going from
  54 to 1,128 documents.
- **Duplicates and versions.** Near-duplicate passages fill the top-k with
  the same evidence. Embeddings carry no sense of time or authority, so an
  outdated version ranks as high as the current one.
- **Corpus rot.** Quality drifts down as stale content piles up, with no
  change to the model.
- **Index tuning.** HNSW settings tuned at 1M vectors give lower recall at
  100M unless retuned.
- **Reranking cost** grows with candidates per query, not corpus size, so
  it is a latency budget question rather than a scale one.

### What decides it

Breadth of the corpus (how many topics share one index), how much of it is
duplicated or versioned, and whether queries can be narrowed before the
vector search.

### Where it bites

Broad, growing corpora with many versions of the same content. The fixes
are narrowing first (by category, source or date, then search within),
dedup and a version rule at ingest, and pruning stale content.

### askRAG today

1,046 indexed papers, densest in one window of months, each paper one
version. Dilution becomes the main risk if the indexed set grows toward
the whole catalog; the defence is the category and date filters that
`search_corpus` already passes into the vector search (D8).

## Disk and RAM by vector count

### What decides it

```
size ≈ vectors × dims × bytes_per_number
     + index links (HNSW, M = 16: about 130-160 B per vector)
     + payload (stored chunk text and metadata)
```

Chunking sets the vector count: vectors = documents × chunks per document.
Halving the chunk size roughly doubles everything above.

A billion vectors, raw numbers only (*computed*):

| Dims | float32 | float16 | int8 | binary |
|---|---|---|---|---|
| 512 | 2.0 TB | 1.0 TB | 0.5 TB | 64 GB |
| 768 | 3.1 TB | 1.5 TB | 0.77 TB | 96 GB |
| 1536 | 6.1 TB | 3.1 TB | 1.5 TB | 192 GB |

On top of that, HNSW links add about 150 GB per billion, and a 500-token
chunk stored next to its vector is about 2 KB, another 2 TB per billion:
the payload often matches or exceeds the vectors.

### Where it bites

In-memory HNSW needs the vector bytes in RAM, which is why billion-scale
stores quantize, use disk-based indexes (DiskANN, IVF-PQ) or move to object
storage. See "HNSW memory" in `docs/vector-db/README.md`.

### askRAG today

1,046 papers made 65,401 chunks, about 62 per paper: 65,401 × 512 × 4 B is
134 MB of raw vectors (*computed*). The paper map holds one vector per
abstract: 89,628 × 512 × 4 B is 183 MB, which matches the file on disk.
All of arXiv (about 2.5M papers) chunked the same way would be about 155M
vectors: roughly 320 GB at float32, 40 GB at int8 (*computed*).

## Document types

### What happens

Parsing decides retrieval quality before any retriever runs: if extraction
garbles a page, every method downstream inherits the mess.

| Type | What breaks | What works |
|---|---|---|
| Prose | little | fixed 256-512 token chunks |
| PDFs with layout (two columns, papers) | reading order scrambles; headers and footers become noise | layout-aware parsing, strip boilerplate, check parser output before embedding |
| Tables | a value without its column header, row label or unit means nothing; tables split at page breaks | keep each table whole and repeat headers in each piece, or query spreadsheets as structured data |
| Scanned PDFs | OCR errors flow into the chunks | clean images before OCR, flag low-confidence extractions |
| Figures and charts | text chunking skips them | visual retrieval, or captions and descriptions |
| Code | splitting mid-function | split at function and class boundaries |

### Where it bites

Mixed corpora. Keep a test set of the awkward cases (tables, scanned
pages, multi-column pages): a bad extraction makes every retrieval method
look worse than it is.

### askRAG today

arXiv papers are two-column PDFs with tables, equations and figures, so
parsing (D6) matters more than the store. Where the eval misses fall by
content type (tables, figures, equations, prose) is not yet broken down.

## Graph RAG

### What happens

GraphRAG (Microsoft) and LightRAG have an LLM extract entities and
relationships into a graph and summarise communities of related entities.

- **Wins** on whole-corpus questions ("what are the main themes?") and
  multi-hop questions.
- **Loses** on single-fact lookups, which plain vector RAG answers better.

### What decides it

Cost. Indexing is reported at 100-1,000x vector RAG; LazyGraphRAG defers
the LLM work to query time and reportedly matches vector RAG's indexing
cost. Query cost bites harder: one benchmark measured about 331,000 tokens
per global question against 879 for vector RAG. LightRAG's reported 66.7%
win rate drops to about 39% after one review corrected the evaluation.

### Where it bites

The common advice: start with hybrid search plus a reranker, and add a
graph only where your own evals show failures. Cognee is a graph-plus-vector
memory layer for agents in the same family; its benchmark claims are mostly
its own.

### askRAG today

The citation graph is already a relationship graph, exact and cheap,
unlike one an LLM extracts. "Papers that cite X" questions could use it
without GraphRAG's cost.

## Visual RAG

### What happens

ColPali and ColQwen embed page images directly, with no text extraction:
strongest on visually rich documents.

### What decides it

Storage and scoring. ColPali makes 1,024 vectors of 128 dims per page,
about 512 KB per page in float32. It needs a store with multi-vector
support (Qdrant, Milvus, Vespa), and late-interaction scoring is slower.
For mostly-text documents, BM25 plus text embeddings stays cheaper and is
about as good.

### askRAG today

About 15 pages per paper × 512 KB is roughly 8 GB for 1,046 papers,
against 134 MB of text vectors (*computed*). Worth it only if figures and
tables turn out to be where the eval misses.

## Cache-augmented generation

### What happens

CAG loads the whole knowledge base into the model's context once and
caches it, so there is no retrieval step.

### Where it bites

Only works when the corpus fits the context window and rarely changes.
Cheaper at high query volume on a stable corpus; not viable for a large or
changing one.

### askRAG today

Not applicable: 65,401 chunks are far beyond any context window.

## Sources

- Scale: [Vector search dilution paper](https://arxiv.org/pdf/2606.11350) · [Why RAG quality breaks at scale](https://whyaiman.substack.com/p/why-rag-quality-breaks-at-scale) · [Corpus curation](https://tianpan.co/blog/2026-04-14-corpus-curation-rag-document-quality-floor) · [New Stack on scaling retrieval](https://thenewstack.io/rag-retrieval-scaling-architecture/) · [EyeLevel on accuracy at scale](https://eyelevel.ai/post/do-vector-databases-lose-accuracy-at-scale)
- Document types: [Oracle on tables, PDFs and media](https://blogs.oracle.com/developers/rag-chunking-and-parsing-for-tables-pdfs-transcripts-and-media) · [CustomGPT PDF chunking](https://customgpt.ai/chunking-strategies-for-pdf-documents-in-rag-systems/) · [Omdena parsing](https://www.omdena.com/blog/document-parsing-for-rag) · [apxml chunking](https://apxml.com/courses/optimizing-rag-for-production/chapter-2-advanced-retrieval-optimization/optimizing-chunking-strategies-rag)
- GraphRAG: [premai](https://blog.premai.io/graphrag-implementation-guide-entity-extraction-query-routing-when-it-beats-vector-rag-2026) · [tianpan.co](https://tianpan.co/blog/2026-04-09-graphrag-production-when-vector-search-hits-ceiling) · [beri.net cost analysis](https://www.beri.net/article/graphrag-vs-vector-rag-indexing-query-cost-lightrag-lazygraphrag-2026) · [Memgraph on Cognee](https://memgraph.com/blog/from-rag-to-graphs-cognee-ai-memory)
- Visual RAG: [ColPali paper](https://arxiv.org/pdf/2407.01449v1) · [Visual RAG Toolkit](https://arxiv.org/html/2602.12510) · [Zilliz on ColPali](https://zilliz.com/blog/colpali-enhanced-doc-retrieval-with-vision-language-models-and-colbert-strategy)
- CAG: [RAG vs CAG](https://theneuralmaze.substack.com/p/rag-vs-cag-a-deep-technical-breakdown) · [CAG scenarios](https://aiexpjourney.substack.com/p/smarter-not-harder-why-cag-outshines)
