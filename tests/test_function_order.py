"""Structural tests for readable module-level helper ordering."""

import ast
from pathlib import Path


PACKAGE_DIR = Path(__file__).parents[1] / "src" / "semaphore_ui"


def test_private_helpers_precede_their_module_level_callers():
    """Require module-local private helpers to appear before their callers."""
    for module_path in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for caller_name, caller in functions.items():
            for node in ast.walk(caller):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                callee = functions.get(node.func.id)
                if callee is None or not callee.name.startswith("_"):
                    continue
                assert callee.lineno <= caller.lineno, (
                    f"{module_path.name}: {caller_name} must follow its helper {callee.name}"
                )
