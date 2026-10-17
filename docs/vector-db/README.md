# Vector DB notes

Source material for the Documentation tab's Vector DB page (not built yet).
Each entry answers one "when does the store matter" question: what happens,
what decides it, where it bites, and what it means for askRAG today. Add an
entry when a store question gets researched; the page is built from these.

Numbers marked *measured* were observed on this repo; the rest are computed
or come from the linked sources.

## HNSW memory

### What gets loaded

HNSW is a graph: every vector is a node linked to its nearest neighbours.
A query walks it, hop by hop, and each hop reads a node's neighbour list
and the vectors of those neighbours to compute distances. One query makes
roughly 1,000 to 2,000 hops that land in unpredictable places, so search is
thousands of small random reads. That is why it wants RAM:

| Where the data sits | One random read | ~2,000 reads (one query) |
|---|---|---|
| RAM | ~0.1 µs | ~0.2 ms |
| SSD | ~100 µs | ~200 ms |
| Object storage (S3) | ~10-50 ms | seconds |

Stores differ in what they load and when:

- **hnswlib, and Chroma on top of it**: loads the whole index (every vector
  plus every link) into RAM when the collection is opened, and keeps it
  there. Chroma's docs: the index "must reside in system RAM to query or
  update".
- **pgvector**: the index lives in 8 KB Postgres pages and is read on
  demand through `shared_buffers` and the OS page cache. What is "loaded" is
  whatever searches touch; it stays fast only while that working set stays
  cached.
- **Disk-based indexes (DiskANN, IVF-PQ in LanceDB) and object-storage
  stores (turbopuffer)**: keep a small compressed copy in RAM to steer the
  search, and read full vectors from SSD or S3 in a few large reads.

### What decides how much

Per vector, in hnswlib's layout:

```
bytes ≈ dims × bytes_per_number      the vector itself
      + 2·M × 4 + 4                  bottom-layer links (M = max_neighbors)
      + ~(M × 4 + 4) / (M − 1)       upper layers (a node reaches them with probability 1/M)
      + 8 to 16                      id label and bookkeeping
```

The levers, largest first:

1. **Number of vectors.** Set by chunking: documents × chunks per document.
   Halving the chunk size roughly doubles the index.
2. **Dimensions.** Set by the embedding model (and its MRL cut, D5).
3. **Bytes per number.** float32 is 4, float16 2, int8 1, binary 1/8.
   Quantization is the usual way out of a memory wall, at some recall cost.
4. **M (max neighbours).** Each step adds 8 bytes per vector at the bottom
   layer. Higher M improves recall and costs memory and build time.
5. **Copies.** Every collection opened at once, every tenant's index,
   every replica, and every older generation still loaded counts in full.

Not in RAM for an HNSW store, usually: the chunk text and metadata (Chroma
keeps those in SQLite on disk). `ef_search` changes how much a query
*touches*, not how much is resident; its per-query scratch space is small
(a visited list of about 2 bytes per vector, plus heaps of `ef` entries).

### Where it bites

- **The index outgrows RAM.** Nothing errors. The OS starts paging parts of
  the index to and from disk and query latency jumps from milliseconds to
  hundreds of milliseconds (Chroma's docs: latency "spike[s] rapidly").
- **A container memory limit.** If one is set below the index size, the
  process is OOM-killed instead of slowing down.
- **Index builds.** pgvector builds the graph in `maintenance_work_mem`;
  when it no longer fits, it logs `hnsw graph no longer fits into
  maintenance_work_mem` and the build slows several-fold (one report:
  17 s to 64 s for 200k vectors at 256 dims).
- **Many collections or tenants.** Each one opened is loaded in full.
  Chroma documents an LRU unload (`CHROMA_SEGMENT_CACHE_POLICY=LRU` with
  `CHROMA_MEMORY_LIMIT_BYTES`) for 0.4 to 0.6; not verified on the 1.5.9
  we pin.
- **Cold start.** Loading the index on open takes time proportional to its
  size; the first query after a restart pays it.
- **Cost at scale.** RAM runs about $5 per GB-month in the cloud against
  about $0.02 for object storage. A billion float32 vectors are 2 TB at
  512 dims and 6.1 TB at 1536 dims, before links. This is where stores
  split: quantize, go disk-based, or go to object storage.

### askRAG today

- 65,401 chunk vectors (1,046 papers, about 62 chunks each) at 512 dims,
  float32, Chroma HNSW with `max_neighbors` 16 (D4, D5).
- Computed: 2,048 B vector + 132 B bottom links + about 13 B upper layers
  and label ≈ 2.2 KB per vector, so **about 145 MB** resident, of which
  134 MB is the raw vectors.
- *Measured*: `corpus/chroma` is 905 MB on disk, which holds more than one
  collection folder; how much of that is live has not been checked. The
  host has 23 GiB of RAM and the deploy sets no container memory limit.
- Verdict: far from every threshold above. The question to recheck is the
  number of vectors, if chunking gets finer or the indexed set widens
  toward the whole catalog (about 41,500 papers with text would be about
  2.6M vectors, about 5.7 GB at today's chunking).

### Sources

- [Chroma: performance (HNSW must reside in RAM)](https://docs.trychroma.com/guides/deploy/performance)
- [Chroma cookbook: memory management (LRU settings)](https://cookbook.chromadb.dev/strategies/memory-management/)
- [Chroma cookbook: resource requirements](https://cookbook.chromadb.dev/core/resources/)
- [Chroma: collection configuration (HNSW defaults)](https://docs.trychroma.com/docs/collections/configure)
- [pgvector HNSW docs (maintenance_work_mem)](https://docs.pgedge.com/pgvector/v0-8-5/hnsw/)
- [pgvector HNSW on a small VPS (build slowdown)](https://www.ssdnodes.com/learn/pgvector-hnsw-index-on-a-small-vps)
- [ClickHouse: scaling pgvector (memory, working set)](https://clickhouse.com/resources/engineering/scale-vector-search-postgres)
- [Disk vs in-memory ANN indexes](https://towardsdatascience.com/optimizing-vector-search-on-disk-vs-in-memory-ann-indexes-when-ram-gets-too-expensive/)
- [turbopuffer: object-storage-first architecture](https://jxnl.co/writing/2025/09/11/turbopuffer-object-storage-first-vector-database-architecture/)

## Retrieval quality

### What happens

Every store named here (pgvector, Chroma, Qdrant, Milvus, Weaviate) searches
with HNSW by default, which is approximate: it can miss a true neighbour.
An exact scan (no index) returns the same top-k in any store for the same
vectors and distance, at recall 1.0.

### What decides it

Index settings, not the brand: `ef_search` at query time and `M` at build
time. Defaults differ (pgvector `ef_search` 40, Chroma 100, Chroma's
distributed SPANN 200), so stores left at defaults show different recall on
identical data. Matched settings should give similar recall; no independent
head-to-head was found that proves it.

### Where it bites

- Comparing stores at their defaults and reading the gap as the store's.
- Public benchmarks: ANN-benchmarks is single-threaded on synthetic sets
  (GloVe, SIFT) with no filters; VectorDBBench is built by Zilliz (Milvus),
  its public results date from 2023-2024 and leave out Chroma; vendors
  dispute each other's numbers.
- Above about 0.95 recall the difference is rarely visible in RAG answers,
  and BM25 plus a reranker in a hybrid stack recovers most misses.

### askRAG today

Chroma, cosine, `ef_search` 100, `max_neighbors` 16
(`backend/askrag/ingest/build_indexes.py`). At 65,401 vectors an exact numpy
scan takes milliseconds, so the HNSW miss rate can be measured against it on
the golden set; not measured yet. Swapping stores would not move the
`just eval` table unless HNSW is the thing missing passages.

### Sources

- [ANN-Benchmarks paper](https://arxiv.org/pdf/1807.05614) · [ann-benchmarks.com](https://ann-benchmarks.com/)
- [VectorDBBench](https://pypi.org/project/vectordb-bench/) · [Zilliz: Milvus vs Qdrant benchmark divergence](https://zilliz.com/blog/demystify-benchmark-result-divergence-milvus-vs-qdrant)
- [MariaDB: 10-database vector benchmark](https://mariadb.org/big-vector-search-benchmark-10-databases-comparison/)
- [Percona: benchmarking vector indexes](https://percona.com/blog/benchmarking-vector-indexes)
- [Chroma: collection configuration](https://docs.trychroma.com/docs/collections/configure)

## Filtered search

### What happens

"Nearest chunks, but only cs.CL from 2026." The store either filters
inside the graph walk (skipping nodes that fail) or after it (walk first,
drop failures). Filtering after returns too few results when the filter is
selective: pgvector with `ef_search` 40 and a filter matching 10% of rows
returns about 4 rows for `LIMIT 10`.

### What decides it

- **pgvector**: filters after the index pass by default. 0.8 added
  iterative scans (`hnsw.iterative_scan`, strict or relaxed order) that keep
  walking until enough rows match or `hnsw.max_scan_tuples` is hit, after
  which it can still return short. Workarounds: a B-tree on the filter
  column for very selective filters, partial HNSW indexes per value, or
  partitioning by the filter key.
- **Qdrant, Milvus, Weaviate**: filter inside the search natively (Qdrant
  builds extra graph links per indexed payload field).
- **Chroma**: takes a `where` clause on metadata; how its local HNSW applies
  it (inside the walk or by brute force over the matching set) is not
  verified here.

### Where it bites

- Selective filters (one category, one month, a small paper set) on large
  collections: short or missing results with no error.
- A 2026 study found Postgres's planner often picks the approximate index
  even when an exact scan would match its latency at full recall, and that
  IVFFlat can beat HNSW at low selectivity.

### askRAG today

Live: `search_corpus` pushes category, year range and paper scope into
Chroma's `where` (`backend/askrag/retrieval/vector_store.py`, D8). With
65,401 vectors even a brute-force scan of the matching set is cheap; worth a
check that a narrow scope (one paper's chunks) still returns `k` results.

### Sources

- [pgvector iterative index scans](https://docs.pgedge.com/pgvector/v0-8-5/iterative-index-scans/)
- [AWS: pgvector 0.8 on Aurora](https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql)
- [Filtered ANN in vector databases (2026)](https://arxiv.org/html/2602.11443v1)
- [Crunchy Data: hybrid search with pgvector](https://www.crunchydata.com/blog/hybrid-vector-search)
- [ClickHouse: scaling pgvector](https://clickhouse.com/resources/engineering/scale-vector-search-postgres)

## Multi-tenancy

### What happens

Many customers share one deployment and each searches only their own
vectors. Either every tenant gets its own collection or index (strong
isolation, each one loaded in full, see HNSW memory), or all tenants share
one index with a tenant field that every query filters on (cheap, but
filtered search above applies).

### What decides it

- **Qdrant**: one collection with a tenant id in the payload; from 1.16,
  small tenants share a fallback shard and large ones get dedicated shards.
- **Weaviate**: native tenants, one shard each.
- **Milvus**: a partition key routes each tenant to its own partition.
- **pgvector**: Postgres row-level security or table partitioning; how RLS
  interacts with HNSW index use was not found in any source.
- **turbopuffer**: built around very many cheap namespaces on object storage.

None of these replace authentication: the store partitions data, the app
still decides who may query which tenant.

### Where it bites

- Thousands of per-tenant collections in an in-memory store.
- One shared index where a single huge tenant skews results or latency for
  the rest.

### askRAG today

Not applicable: one public corpus, no tenants.

### Sources

- [Qdrant: multitenancy and custom sharding](https://qdrant.tech/articles/multitenancy/index.md)
- [Qdrant: multitenant search](https://qdrant.tech/documentation/production-operations/multitenant-search/index.md)
- [Qdrant: collection per tenant or payload partitioning](https://oneuptime.com/blog/post/2026-08-28-qdrant-one-collection-per-tenant-or-payload-partitioning/markdown)
- [vectordb: multi-tenancy across stores](https://mintlify.com/avnlp/vectordb/data/multi-tenancy)

## Vector types and hybrid search

### What happens

All of these take any dense float vector, dimension fixed per collection or
column. They differ in the ceiling, smaller number formats (memory, see
HNSW memory), sparse vectors (BM25 or SPLADE weights for keyword-style
search) and multi-vectors (one vector per token, ColBERT-style).

| | Max dense dims | Element types | Sparse | Multi-vector |
|---|---|---|---|---|
| pgvector | 16,000 stored; indexed 2,000 (`vector`), 4,000 (`halfvec`), 64,000 (`bit`) | float32, float16, binary | `sparsevec`, 1,000 non-zero indexed | no |
| Chroma | none documented | float32 | BM25 / SPLADE via the Search API; documented under Cloud, local not confirmed | no |
| Qdrant | 65,535 (configurable) | float32, float16, uint8 | yes | yes |
| Milvus | 32,768 default (`proxy.maxDimension`; third-party source) | float32, float16, bfloat16, int8 (HNSW only), binary | yes | yes |

Built-in dense plus sparse or BM25 fusion: Weaviate, Qdrant, Milvus,
Elasticsearch/OpenSearch. pgvector does it in SQL with Postgres full-text
search.

### Where it bites

- A model above pgvector's 2,000-dim index cap (3,072-dim embeddings need
  `halfvec` or an MRL cut).
- Moving to late-interaction (ColBERT) retrieval: only Qdrant and Milvus
  store it natively.

### askRAG today

512-dim float32 fits every row. Hybrid search is two stores fused in code:
Chroma for vectors, SQLite FTS5 for BM25, joined by RRF (D8).

### Sources

- [pgvector dimension limits](https://fast.io/resources/pgvector-max-vector-size.md)
- [Qdrant FAQ](https://qdrant.tech/documentation/faq/qdrant-fundamentals/index.md)
- [PyMilvus data types](https://tessl.io/registry/tessl/pypi-pymilvus/2.6.0/files/docs/types-enums.md) · [Milvus limits](https://fast.io/resources/milvus-limits.md)
- [Chroma sparse vector search](https://docs.trychroma.com/cloud/schema/sparse-vector-search)

## Choosing a store

### What decides it

Below a few million vectors with simple queries, any store gives the same
results at similar speed, and the question is which database is already
running. Past that, the entries above decide it.

| Store | Chosen when |
|---|---|
| pgvector | Postgres is already there; up to tens of millions of vectors (50-100M with pgvectorscale); vectors in the same transaction as the rows |
| Chroma | Embedded, no server; prototypes and small RAG; basic filtering |
| Qdrant | Self-hosted with heavy filtering, multi-tenancy, dense plus sparse, quantization for tight memory |
| Milvus | Billion scale, GPU indexes, the most index types; the heaviest to operate |
| Weaviate | Built-in hybrid search and per-tenant shards |
| Pinecone | Managed, no operations, small to medium corpora; pay per read and write |
| turbopuffer / LanceDB | Very large or many-namespace corpora on object storage; cost over tail latency |
| Elasticsearch / OpenSearch | Already running for keyword search |

Also deciding: write churn (re-embedding bloats Postgres tables through
MVCC) and transactional consistency (pgvector keeps vectors and rows in one
transaction; a separate store has to be kept in sync).

### askRAG today

D4 (SQLite plus embedded Chroma, no database server) fits: 65,401 vectors,
one box, no tenants, simple filters. Revisit if any of: the indexed set
widens toward the whole catalog (about 2.6M vectors), Postgres arrives for
another reason, or filtered vector search starts returning short.

### Sources

- [Firecrawl: best vector databases 2026](https://www.firecrawl.dev/blog/best-vector-databases)
- [DEV: choosing a vector database in 2026](https://dev.to/arya_koste_5845807df94776/choosing-a-vector-database-in-2026-pgvector-vs-pinecone-vs-qdrant-vs-weaviate-vs-milvus-422k)
- [Encore: vector database comparison](https://encore.dev/articles/best-vector-databases)
- [pgvector vs Qdrant vs Weaviate at 100M vectors](https://blog.elest.io/pgvector-vs-qdrant-vs-weaviate-which-vector-database-holds-up-at-100m-vectors/)
- [Next Platform: vector search cost](https://www.nextplatform.com/store/2026/09/22/vector-search-is-now-a-data-type-but-the-money-math-has-not-gone-away/5298393)
