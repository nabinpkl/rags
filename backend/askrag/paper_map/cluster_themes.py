"""Themes: HDBSCAN regions in the 10-d layout, named by their distinctive words.

Names are class TF-IDF keywords (a cluster's word counts against every
cluster's), not prose, which is why the page says the grouping is AI-made
and may be wrong. -1 is HDBSCAN's "no region" and stays unthemed: nearest
centre assignment was measured wrong on 6 of 15 papers (docs/themes).
"""

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer

NO_THEME = -1


def cluster(z: np.ndarray, min_cluster_size: int, min_samples: int) -> np.ndarray:
    return HDBSCAN(
        min_cluster_size=min_cluster_size, min_samples=min_samples, copy=True
    ).fit_predict(z)


def theme_words(docs: list[str], labels: np.ndarray, k: int = 8) -> dict[int, list[str]]:
    """Top `k` class TF-IDF terms (unigrams and bigrams) per cluster."""
    clusters = sorted(set(labels.tolist()) - {NO_THEME})
    min_df = max(1, min(20, len(docs) // 50))
    cv = CountVectorizer(
        stop_words="english", ngram_range=(1, 2), min_df=min_df, max_features=40000
    )
    m = cv.fit_transform(docs)
    vocab = np.array(cv.get_feature_names_out())
    counts = np.vstack([np.asarray(m[labels == c].sum(0)).ravel() for c in clusters]).astype(float)
    tf = counts / counts.sum(1, keepdims=True)
    idf = np.log(1 + counts.sum(1).mean() / (counts.sum(0) + 1))
    score = tf * idf
    return {c: list(vocab[np.argsort(-score[i])[:k]]) for i, c in enumerate(clusters)}


def theme_name(words: list[str], n: int) -> str:
    """The first `n` words that repeat none already taken ("gaussian splatting"
    after "gaussian" and "splatting" adds nothing), joined with a middle dot."""
    taken: list[str] = []
    for w in words:
        parts = set(w.split())
        if any(parts <= set(t.split()) or set(t.split()) <= parts for t in taken):
            continue
        taken.append(w)
        if len(taken) == n:
            break
    return " · ".join(taken)
