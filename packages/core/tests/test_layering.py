"""Core must not depend on any application layer (cli, and later server).

The distribution boundary is only real if the import direction is. This walks
the core source and asserts no module reaches into ``pytodo.cli`` (or a future
``pytodo.server``). The ruff banned-api rule catches the same thing at edit
time; this is the guarantee that survives in CI.
"""

import ast
from pathlib import Path

CORE_SRC = Path(__file__).resolve().parents[1] / "src" / "pytodo" / "core"
FORBIDDEN = ("pytodo.cli", "pytodo.server")


def _imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_core_never_imports_an_application_layer():
    offenders = []
    for path in CORE_SRC.rglob("*.py"):
        for name in _imported_modules(path):
            if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                offenders.append(f"{path.name}: {name}")
    assert not offenders, "core imports a forbidden layer: " + ", ".join(offenders)
