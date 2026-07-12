"""Placeholder proving the uv-workspace wiring (issue #79).

Importing askrag's read seams here must resolve from the shared workspace
venv with no second torch/chromadb install. #17 deletes this file once
golden_set.py / draft_golden_set.py land in its place.
"""

from askrag.db import connect_corpus
from askrag.retrieval.hybrid_search import HybridSearch

__all__ = ["HybridSearch", "connect_corpus"]
