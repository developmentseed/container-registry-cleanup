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


class TestSettings:
    def test_dry_run_parsing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test DRY_RUN boolean parsing from environment."""
        monkeypatch.setenv("DRY_RUN", "true")
        settings = Settings()
        assert settings.DRY_RUN is True

        monkeypatch.setenv("DRY_RUN", "false")
        settings = Settings()
        assert settings.DRY_RUN is False
