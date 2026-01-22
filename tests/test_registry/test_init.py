"""Tests for registry initialization."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from container_registry_cleanup.registry import GHCRClient, init_registry
from container_registry_cleanup.settings import Settings


class TestInitRegistry:
    def test_init_ghcr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test GHCR registry initialization."""
        monkeypatch.setenv("GITHUB_TOKEN", "token")
        monkeypatch.setenv("ORG_NAME", "org")

        settings = Settings()
        settings.registry_type = "ghcr"
        settings.repository_name = "repo"

        registry, info = init_registry(settings)
        assert isinstance(registry, GHCRClient)
        assert "GHCR" in info

    def test_init_invalid_registry(self) -> None:
        """Test invalid registry type raises error."""
        settings = Settings()
        settings.registry_type = "invalid"
        settings.repository_name = "repo"

        with pytest.raises(ValueError, match="REGISTRY_TYPE"):
            init_registry(settings)
