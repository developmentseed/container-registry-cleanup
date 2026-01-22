"""Tests for settings module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from container_registry_cleanup.settings import Settings


class TestTagPatterns:
    def setup_method(self) -> None:
        self.settings = Settings()

    def test_test_pattern(self) -> None:
        assert self.settings.compiled_test_pattern.match("pr-123")
        assert self.settings.compiled_test_pattern.match("pr-9999")
        assert not self.settings.compiled_test_pattern.match("pr-abc")
        assert not self.settings.compiled_test_pattern.match("pr123")

    def test_version_pattern(self) -> None:
        assert self.settings.compiled_version_pattern.match("v1.0.0")
        assert self.settings.compiled_version_pattern.match("v2.3.4-beta")
        assert self.settings.compiled_version_pattern.match("1.0.0")
        assert self.settings.compiled_version_pattern.match("0.8.1")
        assert self.settings.compiled_version_pattern.match("latest")
        assert not self.settings.compiled_version_pattern.match("v1")
        assert not self.settings.compiled_version_pattern.match("20240101-120000")

    def test_dev_pattern(self) -> None:
        assert self.settings.compiled_dev_pattern.match("dev")
        assert self.settings.compiled_dev_pattern.match("main")
        assert self.settings.compiled_dev_pattern.match("sha-abc123")
        assert self.settings.compiled_dev_pattern.match("sha-1234567890abcdef")
        assert not self.settings.compiled_dev_pattern.match("sha-xyz")
        assert not self.settings.compiled_dev_pattern.match("sha-123-abc")
        assert not self.settings.compiled_dev_pattern.match("develop")
        assert not self.settings.compiled_dev_pattern.match("main-branch")


class TestSettings:
    def test_dry_run_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test dry_run boolean parsing from environment."""
        monkeypatch.setenv("DRY_RUN", "true")
        settings = Settings()
        assert settings.dry_run is True

        monkeypatch.setenv("DRY_RUN", "false")
        settings = Settings()
        assert settings.dry_run is False
