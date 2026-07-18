"""The server is a frontend on core; it must not import a sibling frontend.

Same guard as core's: the distribution boundary is only real if the import
direction is. The server may use ``neverland.core`` but never ``neverland.cli``.
"""

import ast
from pathlib import Path

SERVER_SRC = Path(__file__).resolve().parents[1] / "src" / "neverland" / "server"
FORBIDDEN = ("neverland.cli",)


def _imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_server_never_imports_the_cli():
    offenders = []
    for path in SERVER_SRC.rglob("*.py"):
        for name in _imported_modules(path):
            if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                offenders.append(f"{path.name}: {name}")
    assert not offenders, "server imports cli: " + ", ".join(offenders)
