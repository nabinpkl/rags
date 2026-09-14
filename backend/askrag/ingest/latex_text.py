"""LaTeX-escaped catalog metadata -> the text a reader sees.

arXiv submitters type their names and titles in LaTeX, and both of our catalog
sources carry that through verbatim. When this was written, 5,648 `papers`
rows and 5,451 `cited_works` rows held a backslash in `authors`, which is how
`Vil\\'em Zouhar` and `Ond\\v{r}ej Bojar` reached the dashboard's front page.

This converts CATALOG STRINGS; it is not a LaTeX renderer. Math spans are
left exactly as they arrived: `\\v{x}` inside `$...$` is a vector accent, not
a caron, and a converter that guesses between them changes what the author
wrote. Residual `$...$` in a title is honest; a wrong character is not.
"""

import re
import unicodedata

# A backslash before punctuation is never the start of a word command, so
# both `\'e` and `\'{e}` are unambiguous.
_PUNCT_ACCENTS = {
    "'": "\u0301",  # acute
    "`": "\u0300",  # grave
    "^": "\u0302",  # circumflex
    '"': "\u0308",  # diaeresis
    "~": "\u0303",  # tilde
    "=": "\u0304",  # macron
    ".": "\u0307",  # dot above
}

# These share their names with the first letters of real commands, so the
# BRACED form is the only one accepted: `\varepsilon` must survive intact,
# and it would not if `\v` took a bare argument.
_LETTER_ACCENTS = {
    "u": "\u0306",  # breve
    "v": "\u030c",  # caron
    "H": "\u030b",  # double acute
    "c": "\u0327",  # cedilla
    "k": "\u0328",  # ogonek
    "r": "\u030a",  # ring above
    "d": "\u0323",  # dot below
    "b": "\u0331",  # macron below
}

_SPECIAL_LETTERS = {
    "ss": "ß",
    "ae": "æ",
    "AE": "Æ",
    "oe": "œ",
    "OE": "Œ",
    "aa": "å",
    "AA": "Å",
    "dh": "ð",
    "DH": "Ð",
    "th": "þ",
    "TH": "Þ",
    "dj": "đ",
    "DJ": "Đ",
    "o": "ø",
    "O": "Ø",
    "l": "ł",
    "L": "Ł",
    # Dotless i and j exist so an accent can sit where the dot was. By the
    # time one does, NFC composes only the dotted form (í, never ı́), so they
    # resolve to plain letters here and the accent rules compose on top.
    "i": "i",
    "j": "j",
}

# Formatting whose argument IS the text: `\textsc{DiARC}` is the word DiARC.
_TEXT_COMMANDS = (
    "textsc",
    "textbf",
    "textit",
    "textrm",
    "texttt",
    "textnormal",
    "emph",
    "text",
    "mathrm",
    "mathbf",
    "bm",
)

# `\&`, `\_`, `\ ` — a backslash before one of these means the character
# itself, not a command.
_ESCAPED_PUNCT = re.compile(r"\\([&_%#$ {}])")
_MATH_SPAN = re.compile(r"(\$[^$]*\$)")
_TEXT_COMMAND = re.compile(r"\\(?:" + "|".join(_TEXT_COMMANDS) + r")\s*\{([^{}]*)\}")
_LETTER_ACCENT = re.compile(
    r"\\([" + "".join(_LETTER_ACCENTS) + r"])\s*\{\s*(\\[ij]|[A-Za-z])\s*\}"
)
# Braced and bare argument are separate alternatives on purpose: only the
# braced form may swallow whitespace before its close. Sharing one optional
# brace ate the space after a bare argument, turning `Universit\'e de` into
# "Universitéde".
_PUNCT_ACCENT = re.compile(r"\\(['`^\"~=.])(?:\{\s*(\\[ij]|[A-Za-z])\s*\}|\s*(\\[ij]|[A-Za-z]))")
_SPECIAL = re.compile(
    # A control word swallows the space that ends it, which is why
    # `Stra\ss e` is one word: Straße.
    r"\\("
    + "|".join(sorted(_SPECIAL_LETTERS, key=len, reverse=True))
    + r")(?![A-Za-z])(?:\{\}|\s)?"
)
_WHITESPACE = re.compile(r"\s+")


def _accented(letter: str, mark: str) -> str:
    base = {"\\i": "i", "\\j": "j"}.get(letter, letter)
    return unicodedata.normalize("NFC", base + mark)


def _convert(text: str) -> str:
    text = _TEXT_COMMAND.sub(r"\1", text)
    text = _LETTER_ACCENT.sub(lambda m: _accented(m[2], _LETTER_ACCENTS[m[1]]), text)
    text = _PUNCT_ACCENT.sub(lambda m: _accented(m[2] or m[3], _PUNCT_ACCENTS[m[1]]), text)
    text = _SPECIAL.sub(lambda m: _SPECIAL_LETTERS[m[1]], text)
    # Braces left over from grouping (`{\'E}douard`) carry no meaning once
    # the command inside them is gone. Escaped punctuation resolves after
    # that, so a literal `\{` is not mistaken for one of them.
    text = text.replace("{", "").replace("}", "")
    return _ESCAPED_PUNCT.sub(r"\1", text)


def latex_to_text(raw: str) -> str:
    """One catalog string, converted. Math spans pass through untouched.

    Also collapses the hard-wrapped newlines the Kaggle metadata carries
    mid-name (10,416 `authors` values held one), which is the same defect
    seen from the same source.
    """
    converted = "".join(
        part if part.startswith("$") else _convert(part) for part in _MATH_SPAN.split(raw)
    )
    return _WHITESPACE.sub(" ", converted).strip()
