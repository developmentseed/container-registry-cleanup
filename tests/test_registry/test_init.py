"""Tests for registry initialization."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from container_registry_cleanup.registry import GHCRClient, HarborClient, init_registry
from container_registry_cleanup.settings import Settings


class TestInitRegistry:
    def test_init_harbor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test Harbor registry initialization."""
        monkeypatch.setenv("HARBOR_URL", "harbor.example.com")
        monkeypatch.setenv("HARBOR_USERNAME", "user")
        monkeypatch.setenv("HARBOR_PASSWORD", "pass")
        monkeypatch.setenv("HARBOR_PROJECT_NAME", "proj")

        settings = Settings()
        settings.REGISTRY_TYPE = "harbor"
        settings.REPOSITORY_NAME = "repo"

        registry, info = init_registry(settings)
        assert isinstance(registry, HarborClient)
        assert "HARBOR" in info

    def test_init_ghcr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test GHCR registry initialization."""
        monkeypatch.setenv("GITHUB_TOKEN", "token")
        monkeypatch.setenv("GITHUB_REPO_OWNER", "org")

        settings = Settings()
        settings.REGISTRY_TYPE = "ghcr"
        settings.REPOSITORY_NAME = "repo"

        registry, info = init_registry(settings)
        assert isinstance(registry, GHCRClient)
        assert "GHCR" in info

    def test_init_invalid_registry(self) -> None:
        """Test invalid registry type raises error."""
        settings = Settings()
        settings.REGISTRY_TYPE = "invalid"
        settings.REPOSITORY_NAME = "repo"

        with pytest.raises(ValueError, match="REGISTRY_TYPE"):
            init_registry(settings)
