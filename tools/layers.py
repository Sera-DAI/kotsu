"""Checks the dependency rule between Kotsu's layers.

    domain   -> nothing (and no I/O module)
    storage  -> domain
    ui       -> domain, storage (but does not talk to SQLite directly)

Usage: python tools/layers.py [package-folder]
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

PACKAGE = "kotsu"
DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "src" / PACKAGE

ALLOWED = {
    "domain": set(),
    "storage": {"domain"},
    "ui": {"domain", "storage"},
}

# External modules forbidden per layer (top-level name).
FORBIDDEN = {
    "domain": {
        "sqlite3",
        "os",
        "io",
        "pathlib",
        "shutil",
        "tempfile",
        "glob",
        "socket",
        "subprocess",
        "urllib",
        "http",
        "requests",
        "textual",
        "rich",
        "sys",
        "importlib",
    },
    "storage": {"textual", "rich"},
    "ui": {"sqlite3"},
}


@dataclass(frozen=True)
class Violation:
    file: Path
    line: int
    layer: str
    imports: str

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}"
        return f"{where}: layer '{self.layer}' must not import '{self.imports}'"


def _module_of_file(file: Path, root: Path) -> list[str]:
    parts = list(file.relative_to(root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return [PACKAGE, *parts]


def _imports(tree: ast.AST, module: list[str], is_package: bool):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                yield node.lineno, name.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: resolve against the current package
                base = module if is_package else module[:-1]
                base = base[: len(base) - (node.level - 1)]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            yield node.lineno, target
            if not node.module or node.level:
                for name in node.names:  # from . import ui
                    yield node.lineno, f"{target}.{name.name}"


def check(root: Path = DEFAULT_ROOT) -> list[Violation]:
    violations = []
    for layer in ALLOWED:
        folder = root / layer
        if not folder.is_dir():
            raise FileNotFoundError(f"layer '{layer}' not found in {root}")
        for file in sorted(folder.rglob("*.py")):
            module = _module_of_file(file, root)
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            for line, target in _imports(tree, module, file.name == "__init__.py"):
                parts = target.split(".")
                if parts[0] == PACKAGE:
                    other = parts[1] if len(parts) > 1 else None
                    if other in ALLOWED and other != layer and other not in ALLOWED[layer]:
                        violations.append(Violation(file, line, layer, target))
                elif parts[0] in FORBIDDEN[layer]:
                    violations.append(Violation(file, line, layer, target))
    return violations


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else DEFAULT_ROOT
    violations = check(root)
    for v in violations:
        print(v)
    print("layers: ok" if not violations else f"layers: {len(violations)} violation(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
