# Theme exploration (2026-10-14)

An exploration toward AI-assigned themes on Explore. Nothing here is wired
into the app yet; it is the evidence for a future decision record.

## What was run

- **Embedding**: title + abstract of the 52,030 catalog papers with ids
  2607-2610, `perplexity/pplx-embed-v1-0.6b` at 512 dims via OpenRouter
  (the corpus embedder). 14.95M tokens, $0.06.
- **Clustering**: UMAP (10 dims, `n_neighbors=30`, `min_dist=0`, cosine,
  seed 7) then HDBSCAN (`min_cluster_size=120`, `min_samples=15`).
  69 clusters, 44% of papers in no cluster.
- **Theme test**: for 13 candidate themes, the 200 papers nearest the
  theme's description and the papers matching a keyword, measured for
  cohesion against random pairs and for how many clusters they spread over.

## Files

- `paper-map.png`: the 52,030 papers in 2D (a separate UMAP run), coloured
  by cluster, grey for no cluster.
- `report.json`: every cluster (size, distinctive words, top categories,
  titles nearest its centre) and the theme test results.

The vectors (107 MB, over GitHub's file limit), ids, labels, 2D coordinates
and the scripts that made them live in `corpus/themes/`, which is gitignored.

## Findings

- Topics that form their own region: agent memory, RAG, reasoning RL, code
  agents, efficient inference (as KV cache, quantization and speculative
  decoding), and, inside the robotics cluster, world models and VLA.
- Aspects that spread across topics: multi-agent, tool use,
  interpretability, benchmarks, surveys. Clustering cannot tag these; a
  per-paper yes/no classifier (Jev) is the candidate.
