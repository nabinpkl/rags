"""Claude Code transcripts as a retrieval source (D21): where the index lives
and the settings every search over it runs under.

The settings pin the local embedder (transcripts are never sent to a hosted
embedding API) and turn the hosted reranker off for live search; the evals
rerank with the local cross-encoder instead (see evals/eval_sources.py).
"""

from askrag.config import Settings
from askrag.retrieval.index_location import IndexLocation


def search_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "embedding_backend": "local",
            "embedding_model": settings.transcripts_embedding_model,
            "embedding_model_revision": settings.transcripts_embedding_revision,
            # fp16 is emulated per-op on a CPU, >30x slower (config.py).
            "embed_local_dtype": "float32",
            "rerank_enabled": False,
        }
    )


def index(settings: Settings) -> IndexLocation:
    local = search_settings(settings)
    return IndexLocation(
        db_path=settings.transcripts_dir / "index.db",
        chroma_dir=settings.transcripts_dir / "chroma",
        collection=local.embedding_model_slug,
    )
