"""Tests for main module."""

import importlib.util
import sys
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_main_path = (
    Path(__file__).parent.parent / "src" / "container_registry_cleanup" / "__main__.py"
)
_main_spec = importlib.util.spec_from_file_location(
    "container_registry_cleanup.__main__", _main_path
)
assert _main_spec is not None
_main_module = importlib.util.module_from_spec(_main_spec)
# Temporarily replace sys.exit to prevent exit during import
_original_exit = sys.exit
sys.exit = cast(Any, lambda _code: None)
try:
    assert _main_spec.loader is not None
    _main_spec.loader.exec_module(_main_module)
finally:
    sys.exit = cast(Any, _original_exit)
main = _main_module.main


def test_main_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that main() returns 0 when REGISTRY_TYPE is set."""
    monkeypatch.setenv("REGISTRY_TYPE", "ghcr")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("REPOSITORY_NAME", "test-repo")
    monkeypatch.setenv("ORG_NAME", "test-org")
    # Mock the registry to avoid actual API calls
    monkeypatch.setattr(
        "container_registry_cleanup.registry.ghcr.GHCRClient.list_images",
        lambda self: [],
    )
    assert main() == 0


class TestMainFunction:
    def test_main_error_handling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main() handles registry initialization errors."""
        monkeypatch.setenv("REGISTRY_TYPE", "invalid")
        assert main() == 1

    def test_main_dry_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main() in dry-run mode."""
        monkeypatch.setenv("REGISTRY_TYPE", "ghcr")
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("REPOSITORY_NAME", "test-repo")
        monkeypatch.setenv("ORG_NAME", "test-org")
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setattr(
            "container_registry_cleanup.registry.ghcr.GHCRClient.list_images",
            lambda self: [],
        )
        assert main() == 0
