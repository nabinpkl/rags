"""The source-agnostic retrieval core (D21): index contract, embedding,
both search legs, fusion and rerank.

It imports nothing from agent/, api/, tools/, ingest/, sources/ or
paper_map/: a source depends on the core, never the reverse
(tests/test_retrieval_boundary.py holds this).
"""
