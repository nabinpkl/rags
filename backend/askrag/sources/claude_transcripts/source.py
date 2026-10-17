"""Claude Code transcripts as a retrieval source (D21): where the index lives
and the settings every search over it runs under.

Embedding is the corpus embedder (the OpenRouter model arXiv uses, owner
directive 2026-10-17), so a session's redacted chunk text and each query
reach OpenRouter; nothing else does. Live search runs without the hosted
reranker; the evals rerank with the local cross-encoder (evals/eval_sources.py).
"""

from askrag.config import Settings
from askrag.retrieval.index_location import IndexLocation


def search_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"rerank_enabled": False})


def index(settings: Settings) -> IndexLocation:
    return IndexLocation(
        db_path=settings.transcripts_dir / "index.db",
        chroma_dir=settings.transcripts_dir / "chroma",
        collection=search_settings(settings).embedding_model_slug,
    )
