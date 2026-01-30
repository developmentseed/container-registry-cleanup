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
    monkeypatch.setenv("GITHUB_REPO_OWNER", "test-org")
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
        monkeypatch.setenv("GITHUB_REPO_OWNER", "test-org")
        monkeypatch.setenv("DRY_RUN", "true")
        monkeypatch.setattr(
            "container_registry_cleanup.registry.ghcr.GHCRClient.list_images",
            lambda self: [],
        )
        assert main() == 0


class TestWriteSummary:
    def test_write_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test write_summary writes to file when GITHUB_STEP_SUMMARY is set."""
        from datetime import UTC, datetime

        from container_registry_cleanup.base import ImageVersion
        from container_registry_cleanup.logic import (
            DeletionPlan,
            ImageDecision,
            write_summary,
        )
        from container_registry_cleanup.settings import Settings

        img1 = ImageVersion("img1", ["tag1"], datetime.now(UTC))
        img2 = ImageVersion("img2", ["tag2"], datetime.now(UTC))
        img3 = ImageVersion("img3abc123def456", ["v1.0", "latest"], datetime.now(UTC))
        plan = DeletionPlan(
            {
                "img1": ImageDecision(img1, "keep", "reason1"),
                "img2": ImageDecision(img2, "keep", "reason2"),
                "img3abc123def": ImageDecision(
                    img3, "delete", "test tag >30d (45d old)"
                ),
            }
        )
        errors = 1

        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))

        settings = Settings()
        settings.DRY_RUN = True
        settings.TEST_RETENTION_DAYS = 30
        settings.OTHERS_RETENTION_DAYS = 7

        write_summary(plan, errors, settings)

        summary_file = tmp_path / "summary.md"
        assert summary_file.exists()
        content = summary_file.read_text()
        assert "Container Image Cleanup" in content
        assert "| Images: kept | 2 |" in content
        assert "| Images: deleted | 1 |" in content
        assert "| Errors | 1 |" in content
        assert "Dry Run" in content
        assert "Test=30d" in content
        assert "Others=7d" in content
        # Check image sections exist with tables
        assert "**To delete: 1 images (2 tags)**" in content
        assert "**To keep: 2 images (2 tags)**" in content
        # Check table headers
        assert "| Image ID | Tags | Type | Reason |" in content
        # Check image details
        assert "`img3abc123de`" in content  # Truncated identifier
        assert "v1.0, latest" in content
        assert "test tag >30d (45d old)" in content
        assert "`img1`" in content
        assert "tag1" in content

    def test_write_summary_live_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test write_summary shows 'Deleted' label in live mode."""
        from datetime import UTC, datetime

        from container_registry_cleanup.base import ImageVersion
        from container_registry_cleanup.logic import (
            DeletionPlan,
            ImageDecision,
            write_summary,
        )
        from container_registry_cleanup.settings import Settings

        img1 = ImageVersion("img1", ["tag1"], datetime.now(UTC))
        img2 = ImageVersion("img2", ["tag2"], datetime.now(UTC))
        img3 = ImageVersion("untagged123", [], datetime.now(UTC))
        img4 = ImageVersion("img4", ["v2.0"], datetime.now(UTC))
        plan = DeletionPlan(
            {
                "img1": ImageDecision(img1, "keep", "reason1"),
                "img2": ImageDecision(img2, "keep", "reason2"),
                "untagged123": ImageDecision(img3, "delete", "untagged >7d (10d old)"),
                "img4": ImageDecision(img4, "delete", "other tag >7d (15d old)"),
            }
        )
        errors = 0

        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))

        settings = Settings()
        settings.DRY_RUN = False
        settings.TEST_RETENTION_DAYS = 30
        settings.OTHERS_RETENTION_DAYS = 7

        write_summary(plan, errors, settings)

        summary_file = tmp_path / "summary.md"
        assert summary_file.exists()
        content = summary_file.read_text()
        assert "Container Image Cleanup" in content
        assert "| Images: kept | 2 |" in content
        assert "| Images: deleted | 2 |" in content
        assert "| Errors | 0 |" in content
        assert "Live" in content
        # Check image sections with "Deleted" label
        assert "**Deleted: 2 images (1 tags)**" in content
        assert "**Kept: 2 images (2 tags)**" in content
        # Check table headers
        assert "| Image ID | Tags | Type | Reason |" in content
        # Check untagged image handling
        assert "`untagged123`" in content
        assert "untagged" in content
        assert "untagged >7d (10d old)" in content
