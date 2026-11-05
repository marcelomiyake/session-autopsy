"""Fitness functions for the dependency rule and the adapter extension boundary."""
import ast
from pathlib import Path
import unittest


class ArchitectureTests(unittest.TestCase):
    def test_inward_dependencies(self):
        root = Path(__file__).resolve().parents[1] / "session_autopsy"
        for layer, forbidden in (("domain", ("application", "adapters", "cli")),
                                 ("application", ("adapters", "cli"))):
            for path in (root / layer).rglob("*.py"):
                for node in ast.walk(ast.parse(path.read_text())):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [node.module or ""]
                    for name in names:
                        self.assertFalse(any(name.startswith("session_autopsy." + f) for f in forbidden), str(path))
                        if layer == "domain":
                            self.assertNotIn(name.split(".")[0], {"urllib", "http", "sqlite3", "subprocess", "os"})
