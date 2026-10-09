"""Names for arXiv's computer science subject classes.

Neither source we ingest names a category: the Kaggle snapshot and the GCS
mirror's `metadata-v5` both carry codes only. The names are copied by hand
from arXiv's taxonomy page (https://arxiv.org/category_taxonomy, checked
2026-09-17), and no code path fetches them (D18, §6b). The build refuses a
corpus holding a `cs.*` code this table does not name, so a class arXiv adds
later stops the build instead of reaching the page unnamed.

Other archives' codes (`math.NA`, `stat.ML`, ...) have no name here; they
show as their code.
"""

CS_CATEGORY_NAMES: dict[str, str] = {
    "cs.AI": "Artificial Intelligence",
    "cs.AR": "Hardware Architecture",
    "cs.CC": "Computational Complexity",
    "cs.CE": "Computational Engineering, Finance, and Science",
    "cs.CG": "Computational Geometry",
    "cs.CL": "Computation and Language",
    "cs.CR": "Cryptography and Security",
    "cs.CV": "Computer Vision and Pattern Recognition",
    "cs.CY": "Computers and Society",
    "cs.DB": "Databases",
    "cs.DC": "Distributed, Parallel, and Cluster Computing",
    "cs.DL": "Digital Libraries",
    "cs.DM": "Discrete Mathematics",
    "cs.DS": "Data Structures and Algorithms",
    "cs.ET": "Emerging Technologies",
    "cs.FL": "Formal Languages and Automata Theory",
    "cs.GL": "General Literature",
    "cs.GR": "Graphics",
    "cs.GT": "Computer Science and Game Theory",
    "cs.HC": "Human-Computer Interaction",
    "cs.IR": "Information Retrieval",
    "cs.IT": "Information Theory",
    "cs.LG": "Machine Learning",
    "cs.LO": "Logic in Computer Science",
    "cs.MA": "Multiagent Systems",
    "cs.MM": "Multimedia",
    "cs.MS": "Mathematical Software",
    "cs.NA": "Numerical Analysis",
    "cs.NE": "Neural and Evolutionary Computing",
    "cs.NI": "Networking and Internet Architecture",
    "cs.OH": "Other Computer Science",
    "cs.OS": "Operating Systems",
    "cs.PF": "Performance",
    "cs.PL": "Programming Languages",
    "cs.RO": "Robotics",
    "cs.SC": "Symbolic Computation",
    "cs.SD": "Sound",
    "cs.SE": "Software Engineering",
    "cs.SI": "Social and Information Networks",
    "cs.SY": "Systems and Control",
}


def category_name(code: str) -> str | None:
    return CS_CATEGORY_NAMES.get(code)


def unnamed_cs_codes(codes: set[str]) -> list[str]:
    """The `cs.*` codes in `codes` this table has no name for, sorted."""
    return sorted(c for c in codes if c.startswith("cs.") and c not in CS_CATEGORY_NAMES)
