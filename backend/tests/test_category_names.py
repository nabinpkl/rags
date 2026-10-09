from askrag.category_names import CS_CATEGORY_NAMES, category_name, unnamed_cs_codes


def test_names_every_cs_class_arxiv_lists():
    # arXiv's taxonomy page listed 40 cs classes on 2026-09-17.
    assert len(CS_CATEGORY_NAMES) == 40
    assert all(code.startswith("cs.") and name for code, name in CS_CATEGORY_NAMES.items())


def test_a_code_reads_as_its_name():
    assert category_name("cs.CL") == "Computation and Language"
    assert category_name("cs.CV") == "Computer Vision and Pattern Recognition"


def test_another_archive_has_no_name_and_is_not_a_gap():
    assert category_name("math.NA") is None
    assert unnamed_cs_codes({"math.NA", "stat.ML", "cs.LG"}) == []


def test_an_unknown_cs_code_is_a_gap():
    assert unnamed_cs_codes({"cs.ZZ", "cs.LG", "cs.AA"}) == ["cs.AA", "cs.ZZ"]
