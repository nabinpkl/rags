import numpy as np

from askrag.paper_map.cluster_themes import NO_THEME, cluster, theme_name, theme_words


def test_cluster_finds_separated_blobs_and_leaves_far_points_unthemed():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.1, (40, 2))
    b = rng.normal(5, 0.1, (40, 2))
    far = np.array([[20.0, -20.0]])
    labels = cluster(np.vstack([a, b, far]), min_cluster_size=10, min_samples=5)
    assert len(set(labels[:40])) == 1 and len(set(labels[40:80])) == 1
    assert labels[0] != labels[40]
    assert labels[80] == NO_THEME


def test_theme_words_rank_each_clusters_distinctive_terms():
    docs = ["robot grasping arm"] * 30 + ["speech audio speaker"] * 30
    labels = np.array([0] * 30 + [1] * 30)
    words = theme_words(docs, labels, k=3)
    assert set(words[0]) <= {"robot", "grasping", "arm", "robot grasping", "grasping arm"}
    assert set(words[1]) <= {"speech", "audio", "speaker", "speech audio", "audio speaker"}


def test_theme_name_skips_terms_already_covered():
    words = ["gaussian", "splatting", "gaussian splatting", "rendering", "3d"]
    assert theme_name(words, 3) == "gaussian · splatting · rendering"


def test_theme_name_skips_a_word_inside_a_taken_bigram():
    assert theme_name(["autonomous driving", "driving", "autonomous", "lidar"], 2) == (
        "autonomous driving · lidar"
    )
