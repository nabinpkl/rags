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
