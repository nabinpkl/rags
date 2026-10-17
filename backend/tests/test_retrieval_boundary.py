"""The retrieval core names no source and no caller (D21).

Read from the import statements themselves, so a lazy import inside a
function is caught too.
"""

import ast
from pathlib import Path

import askrag.retrieval

_FORBIDDEN = ("agent", "api", "tools", "ingest", "sources", "paper_map", "cli", "ask")


def _imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_the_core_imports_no_source_and_no_caller():
    package = Path(askrag.retrieval.__file__).parent
    offenders = {
        f"{path.name}: {module}"
        for path in sorted(package.glob("*.py"))
        for module in _imported_modules(path)
        if module.split(".")[0] == "askrag"
        and len(module.split(".")) > 1
        and module.split(".")[1] in _FORBIDDEN
    }
    assert offenders == set()
