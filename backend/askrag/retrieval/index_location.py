"""Where one source's index lives (D21): its SQLite file and its vector store."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndexLocation:
    """`collection` is the embedding model slug: one model's vectors per
    collection, never a mix (per-model keying, #13/#14)."""

    db_path: Path
    chroma_dir: Path
    collection: str
