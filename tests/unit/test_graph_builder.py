"""Unit tests for the graph builder module."""

from __future__ import annotations

from repograph.core.graph_builder import _extract_module, _infer_language


class TestInferLanguage:
    def test_python(self) -> None:
        assert _infer_language(".py") == "Python"

    def test_typescript(self) -> None:
        assert _infer_language(".ts") == "TypeScript"
        assert _infer_language(".tsx") == "TypeScript"

    def test_javascript(self) -> None:
        assert _infer_language(".js") == "JavaScript"
        assert _infer_language(".jsx") == "JavaScript"

    def test_go(self) -> None:
        assert _infer_language(".go") == "Go"

    def test_unknown(self) -> None:
        assert _infer_language(".xyz") == "Other"

    def test_empty(self) -> None:
        assert _infer_language("") == "Other"


class TestExtractModule:
    def test_two_levels(self) -> None:
        modules = _extract_module("src/core/engine.py", depth=2)
        assert len(modules) == 2
        assert modules[0] == ("src", "src", 0)
        assert modules[1] == ("core", "src/core", 1)

    def test_single_level(self) -> None:
        modules = _extract_module("src/main.py", depth=2)
        assert len(modules) == 1
        assert modules[0] == ("src", "src", 0)

    def test_root_file(self) -> None:
        modules = _extract_module("README.md", depth=2)
        assert len(modules) == 0

    def test_deep_path_capped(self) -> None:
        modules = _extract_module("a/b/c/d/e.py", depth=2)
        assert len(modules) == 2

    def test_depth_one(self) -> None:
        modules = _extract_module("src/core/engine.py", depth=1)
        assert len(modules) == 1
        assert modules[0] == ("src", "src", 0)
