"""Build the paper maps (D20): embed -> layout -> themes -> corpus/paper-map/<scope>/.

`just paper-map` builds every scope in `paper_map_scopes`; `--scope` builds
one. Embeds only papers the shared cache lacks and reuses cached layouts, so
a rerun over an unchanged scope skips UMAP.
"""

import argparse
import logging
import sqlite3
from collections import Counter

import numpy as np

from askrag.config import Settings
from askrag.paper_map.cluster_themes import (
    NO_THEME,
    cluster,
    group_themes,
    theme_name,
    theme_words,
)
from askrag.paper_map.embed_abstracts import embed_abstracts
from askrag.paper_map.export_map import Group, Theme, write_map
from askrag.paper_map.layout_papers import layout


def run(settings: Settings, scope: str) -> None:
    from_month = settings.paper_map_scopes[scope]
    ids, x = embed_abstracts(settings, from_month)
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
                (from_month,),
            )
        }
    finally:
        db.close()
    docs = [f"{meta[a][0]} {meta[a][1]}" for a in ids]
    words = theme_words(docs, labels)

    # Theme indexes run largest first, so the page's colour and label order
    # is the size order without sorting again.
    order = sorted(words, key=lambda c: -int((labels == c).sum()))
    index_of = {c: i for i, c in enumerate(order)}
    theme_index = np.array([index_of.get(int(c), NO_THEME) for c in labels], dtype=np.int16)

    # Umbrella groups over the themes, also indexed largest first.
    centroids = np.stack([x[labels == c].mean(axis=0) for c in order])
    n_groups = max(1, round(len(order) / settings.paper_map_themes_per_group))
    raw_group = group_themes(centroids, n_groups)
    paper_group = np.where(theme_index >= 0, raw_group[np.maximum(theme_index, 0)], NO_THEME)
    group_sizes = {g: int((paper_group == g).sum()) for g in set(raw_group.tolist())}
    group_order = sorted(group_sizes, key=lambda g: -group_sizes[g])
    group_of = {g: i for i, g in enumerate(group_order)}
    group_words = theme_words(docs, paper_group)
    groups = []
    for g in group_order:
        cx, cy = np.median(xy[paper_group == g], axis=0)
        name = theme_name(group_words[g], settings.paper_map_label_words)
        groups.append(Group(group_of[g], name, group_sizes[g], float(cx), float(cy)))

    themes = []
    for c in order:
        m = labels == c
        cx, cy = np.median(xy[m], axis=0)
        top = Counter(meta[ids[i]][3] for i in np.flatnonzero(m)).most_common(1)[0][0]
        name = theme_name(words[c], settings.paper_map_label_words)
        group = group_of[int(raw_group[index_of[c]])]
        themes.append(Theme(index_of[c], name, int(m.sum()), float(cx), float(cy), top, group))

    write_map(
        settings.paper_map_dir / scope,
        ids=ids,
        versions=[meta[a][2] for a in ids],
        titles=[" ".join(meta[a][0].split()) for a in ids],
        xy=xy,
        theme_index=theme_index,
        themes=themes,
        groups=groups,
    )
    unthemed = float((theme_index == NO_THEME).mean())
    print(
        f"{scope}: {len(ids)} papers, {len(groups)} groups, {len(themes)} themes, "
        f"{unthemed:.1%} unthemed"
    )


def main(argv: list[str] | None = None) -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--scope", choices=sorted(settings.paper_map_scopes))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    for scope in [args.scope] if args.scope else settings.paper_map_scopes:
        run(settings, scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
