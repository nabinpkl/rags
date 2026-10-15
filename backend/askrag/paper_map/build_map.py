"""Build the paper map (D20): embed -> layout -> themes -> corpus/paper-map/.

`just paper-map`. Embeds only papers the cache lacks and reuses cached
layouts, so a rerun over an unchanged scope rewrites the same files.
"""

import argparse
import logging
import sqlite3
from collections import Counter

import numpy as np

from askrag.config import Settings
from askrag.paper_map.cluster_themes import NO_THEME, cluster, theme_name, theme_words
from askrag.paper_map.embed_abstracts import embed_abstracts
from askrag.paper_map.export_map import Theme, write_map
from askrag.paper_map.layout_papers import layout


def run(settings: Settings) -> None:
    ids, x = embed_abstracts(settings)
    common = {"neighbors": settings.paper_map_neighbors, "seed": settings.paper_map_seed}
    cache = settings.paper_map_dir
    z = layout(x, ids, cache, dims=settings.paper_map_cluster_dims, min_dist=0.0, **common)
    xy = layout(x, ids, cache, dims=2, min_dist=settings.paper_map_display_min_dist, **common)
    labels = cluster(z, settings.paper_map_min_cluster_size, settings.paper_map_min_samples)

    db = sqlite3.connect(f"file:{settings.corpus_db_path}?mode=ro", uri=True)
    try:
        meta = {
            a: (t, ab, v or "", pc)
            for a, t, ab, v, pc in db.execute(
                "SELECT arxiv_id, title, abstract, version, primary_category FROM papers "
                "WHERE substr(arxiv_id, 1, 4) >= ?",
                (settings.paper_map_from_month,),
            )
        }
    finally:
        db.close()
    words = theme_words([f"{meta[a][0]} {meta[a][1]}" for a in ids], labels)

    # Theme indexes run largest first, so the page's colour and label order
    # is the size order without sorting again.
    order = sorted(words, key=lambda c: -int((labels == c).sum()))
    index_of = {c: i for i, c in enumerate(order)}
    theme_index = np.array([index_of.get(int(c), NO_THEME) for c in labels], dtype=np.int16)
    themes = []
    for c in order:
        m = labels == c
        cx, cy = np.median(xy[m], axis=0)
        top = Counter(meta[ids[i]][3] for i in np.flatnonzero(m)).most_common(1)[0][0]
        name = theme_name(words[c], settings.paper_map_label_words)
        themes.append(Theme(index_of[c], name, int(m.sum()), float(cx), float(cy), top))

    write_map(
        settings.paper_map_dir,
        ids=ids,
        versions=[meta[a][2] for a in ids],
        titles=[" ".join(meta[a][0].split()) for a in ids],
        xy=xy,
        theme_index=theme_index,
        themes=themes,
        from_month=settings.paper_map_from_month,
    )
    unthemed = float((theme_index == NO_THEME).mean())
    print(f"{len(ids)} papers, {len(themes)} themes, {unthemed:.1%} unthemed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    run(Settings())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
