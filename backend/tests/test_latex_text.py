"""Every case here is a string that was actually in the catalog."""

from askrag.ingest.latex_text import latex_to_text


def test_converts_the_accents_the_dashboard_showed_raw():
    assert latex_to_text(r"Vil\'em Zouhar, Ond\v{r}ej Bojar") == "Vilém Zouhar, Ondřej Bojar"
    assert latex_to_text(r"Jean-Fran\c{c}ois Godbout") == "Jean-François Godbout"
    assert latex_to_text(r"No\'emie Elhadad") == "Noémie Elhadad"
    assert latex_to_text(r"Necdet G\"urkan") == "Necdet Gürkan"
    assert latex_to_text(r"Nuno Guimar\~aes") == "Nuno Guimarães"
    assert latex_to_text(r"Ivan Vuli\'c") == "Ivan Vulić"
    assert latex_to_text(r"Thadd\"aus Wiedemer") == "Thaddäus Wiedemer"


def test_handles_every_spelling_of_the_same_accent():
    # Bare, braced argument, and braced group — all three appear in the data.
    assert latex_to_text(r"\'e") == latex_to_text(r"\'{e}") == latex_to_text(r"{\'e}") == "é"
    # Dotless i exists to carry an accent; the composed form is the dotted one.
    assert latex_to_text(r"Mart\'{\i}nez") == "Martínez"
    # A bare argument ends at the letter: the space after it is a real space,
    # and eating it produced "Universitéde la Méditerranée" in the catalog.
    assert latex_to_text(r"Universit\'e de Montr\'eal") == "Université de Montréal"


def test_converts_the_letter_named_accents_and_special_letters():
    assert latex_to_text(r"A P\={a}ninian Foundation") == "A Pāninian Foundation"
    assert latex_to_text(r"\k{a} \u{a} \H{o} \r{a}") == "ą ă ő å"
    assert latex_to_text(r"Stra\ss e, \o, \AA, \L") == "Straße, ø, Å, Ł"


def test_unwraps_formatting_but_leaves_math_alone():
    assert (
        latex_to_text(r"\textsc{DiARC}: Distinguishing Samples") == "DiARC: Distinguishing Samples"
    )
    # A converter that guessed here would have to decide whether `\to` is an
    # arrow or a typo; leaving the span is the honest answer (module docstring).
    assert latex_to_text(r"Original $\to$ Sequel") == r"Original $\to$ Sequel"


def test_leaves_a_word_command_that_merely_starts_with_an_accent_name():
    # THE regression: `\v` takes a braced argument only. Accept a bare one and
    # `\varepsilon` becomes "ǎrepsilon" — a real word, silently wrong.
    assert latex_to_text(r"\varepsilon") == r"\varepsilon"
    assert latex_to_text(r"\cite{x} \over") == r"\citex \over"


def test_collapses_the_hard_wrapped_newlines_the_catalog_carries():
    assert latex_to_text("Jean-Fran\\c{c}ois\nGodbout, Reihaneh Rabbany") == (
        "Jean-François Godbout, Reihaneh Rabbany"
    )


def test_leaves_plain_text_untouched():
    assert latex_to_text("Yuntian Deng, Pengyu Nie, Stuart Shieber") == (
        "Yuntian Deng, Pengyu Nie, Stuart Shieber"
    )
    assert latex_to_text("") == ""
