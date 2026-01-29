"""Tests for logic module."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from container_registry_cleanup.base import ImageVersion
from container_registry_cleanup.logic import (
    _evaluate_tag as evaluate_tag,
    _evaluate_untagged as evaluate_untagged,
    create_deletion_plan,
    execute_deletion_plan,
    print_deletion_plan,
)
from container_registry_cleanup.settings import Settings


class TestRetentionLogic:
    def setup_method(self) -> None:
        s = Settings()
        self.vp = s.compiled_version_pattern
        self.tp = s.compiled_test_pattern

    def test_version_tag_never_deleted(self) -> None:
        should_delete, reason = evaluate_tag(
            "v1.0.0",
            datetime.now(UTC) - timedelta(days=365),
            7,
            30,
            self.vp,
            self.tp,
        )
        assert not should_delete
        assert "version tag" in reason

    def test_test_tag_retention(self) -> None:
        now = datetime.now(UTC)
        should_delete_old, reason_old = evaluate_tag(
            "pr-123", now - timedelta(days=35), 7, 30, self.vp, self.tp
        )
        should_delete_new, reason_new = evaluate_tag(
            "pr-123", now - timedelta(days=10), 7, 30, self.vp, self.tp
        )
        assert should_delete_old
        assert reason_old == "test tag >30d (35d old)"
        assert not should_delete_new
        assert reason_new == "test tag >30d (10d old)"

    def test_dev_tag_retention(self) -> None:
        now = datetime.now(UTC)

        old_dev_tag, reason = evaluate_tag(
            "dev", now - timedelta(days=10), 7, 30, self.vp, self.tp
        )
        assert old_dev_tag
        assert reason == "dev tag >7d (10d old)"

        recent_main_tag, reason = evaluate_tag(
            "main", now - timedelta(days=3), 7, 30, self.vp, self.tp
        )
        assert not recent_main_tag
        assert reason == "dev tag >7d (3d old)"

        old_sha_tag, reason = evaluate_tag(
            "sha-abc123", now - timedelta(days=10), 7, 30, self.vp, self.tp
        )
        assert old_sha_tag
        assert reason == "dev tag >7d (10d old)"

        recent_sha_tag, reason = evaluate_tag(
            "sha-abc123", now - timedelta(days=3), 7, 30, self.vp, self.tp
        )
        assert not recent_sha_tag
        assert reason == "dev tag >7d (3d old)"

    def test_unknown_tag_uses_dev_retention(self) -> None:
        now = datetime.now(UTC)

        old_unknown_tag, reason = evaluate_tag(
            "random-tag", now - timedelta(days=10), 7, 30, self.vp, self.tp
        )
        assert old_unknown_tag
        assert reason == "dev tag >7d (10d old)"

        recent_unknown_tag, reason = evaluate_tag(
            "random-tag", now - timedelta(days=3), 7, 30, self.vp, self.tp
        )
        assert not recent_unknown_tag
        assert reason == "dev tag >7d (3d old)"

    def test_untagged_retention(self) -> None:
        now = datetime.now(UTC)
        old_untagged = now - timedelta(days=10)
        new_untagged = now - timedelta(days=3)

        should_delete_old, reason_old = evaluate_untagged(old_untagged, 7)
        should_delete_new, reason_new = evaluate_untagged(new_untagged, 7)

        assert should_delete_old
        assert reason_old == "untagged >7d (10d old)"
        assert not should_delete_new
        assert reason_new == "untagged >7d (3d old)"

    def test_retention_zero_immediate_deletion(self) -> None:
        """Test that retention=0 causes immediate deletion."""
        now = datetime.now(UTC)
        # Even a brand new tag should be deleted if retention is 0
        should_delete_tag, reason_tag = evaluate_tag(
            "dev", now, 0, 30, self.vp, self.tp
        )
        should_delete_untagged, reason_untagged = evaluate_untagged(now, 0)
        assert should_delete_tag
        assert reason_tag == "dev tag (retention=0d, 0d old)"
        assert should_delete_untagged
        assert reason_untagged == "untagged (retention=0d, 0d old)"


class TestDeletionPlan:
    def setup_method(self) -> None:
        self.settings = Settings()
        # Explicitly set retention days to avoid environment variable interference
        self.settings.DEV_RETENTION_DAYS = 7
        self.settings.TEST_RETENTION_DAYS = 30

    def test_create_plan_all_tags_expired(self) -> None:
        """Image with all tags expired should be deleted entirely."""
        now = datetime.now(UTC)
        images = [ImageVersion("img1", ["dev", "main"], now - timedelta(days=10))]
        plan = create_deletion_plan(images, self.settings)
        assert len(plan.images_to_delete) == 1
        assert len(plan.tags_to_delete) == 0
        assert plan.tags_in_deleted_images == 2

    def test_create_plan_some_tags_expired(self) -> None:
        """Image with some tags expired should delete only those tags."""
        now = datetime.now(UTC)
        images = [ImageVersion("img1", ["v1.0.0", "dev"], now - timedelta(days=10))]
        plan = create_deletion_plan(images, self.settings)
        assert len(plan.images_to_delete) == 0
        assert len(plan.tags_to_delete) == 1
        assert plan.tags_to_delete[0][1] == "dev"
        assert len(plan.tags_to_keep) == 1

    def test_create_plan_no_tags_expired(self) -> None:
        """Image with no tags expired should be kept."""
        now = datetime.now(UTC)
        images = [ImageVersion("img1", ["v1.0.0", "main"], now - timedelta(days=3))]
        plan = create_deletion_plan(images, self.settings)
        assert len(plan.images_to_delete) == 0
        assert len(plan.tags_to_delete) == 0
        assert len(plan.tags_to_keep) == 2

    def test_create_plan_untagged_old(self) -> None:
        """Old untagged image should be deleted."""
        now = datetime.now(UTC)
        images = [ImageVersion("img1", [], now - timedelta(days=10))]
        plan = create_deletion_plan(images, self.settings)
        assert len(plan.images_to_delete) == 1
        assert plan.images_to_delete[0][2] == "untagged"

    def test_create_plan_untagged_new(self) -> None:
        """New untagged image should be kept."""
        now = datetime.now(UTC)
        images = [ImageVersion("img1", [], now - timedelta(days=3))]
        plan = create_deletion_plan(images, self.settings)
        assert len(plan.images_to_delete) == 0


class TestExecuteDeletionPlan:
    def test_empty_plan(self) -> None:
        """Empty plan should return zeros."""
        from container_registry_cleanup.logic import DeletionPlan

        plan = DeletionPlan([], [], [], 0)
        mock_registry = cast(Any, type("MockRegistry", (), {}))
        deleted_images, deleted_tags, errors = execute_deletion_plan(
            mock_registry, plan
        )
        assert deleted_images == 0
        assert deleted_tags == 0
        assert errors == 0

    def test_execute_with_mock_registry(self) -> None:
        """Test execution with mocked registry."""
        mock_registry = MagicMock()
        mock_registry.delete_image = MagicMock()
        mock_registry.delete_tag = MagicMock()

        now = datetime.now(UTC)
        images = [ImageVersion("img1", ["dev"], now - timedelta(days=10))]
        plan = create_deletion_plan(images, Settings())

        deleted_images, deleted_tags, errors = execute_deletion_plan(
            mock_registry, plan
        )
        assert deleted_images == 1
        assert deleted_tags == 0
        assert errors == 0
        mock_registry.delete_image.assert_called_once()


class TestExecuteDeletionPlanErrors:
    def test_execute_plan_with_errors(self) -> None:
        """Test execute_deletion_plan error handling."""
        mock_registry = MagicMock()
        mock_registry.delete_image.side_effect = requests.exceptions.RequestException(
            "API error"
        )
        mock_registry.delete_tag = MagicMock()

        now = datetime.now(UTC)
        settings = Settings()
        settings.DEV_RETENTION_DAYS = 7
        images = [ImageVersion("img1", ["dev"], now - timedelta(days=10))]
        plan = create_deletion_plan(images, settings)

        deleted_images, deleted_tags, errors = execute_deletion_plan(
            mock_registry, plan
        )
        assert deleted_images == 0
        assert errors == 1

    def test_execute_plan_tag_value_error(self) -> None:
        """Test execute_deletion_plan handles ValueError from delete_tag."""
        mock_registry = MagicMock()
        mock_registry.delete_image = MagicMock()
        mock_registry.delete_tag.side_effect = ValueError("Cannot delete tag")

        now = datetime.now(UTC)
        images = [ImageVersion("img1", ["v1.0.0", "dev"], now - timedelta(days=10))]
        plan = create_deletion_plan(images, Settings())

        deleted_images, deleted_tags, errors = execute_deletion_plan(
            mock_registry, plan
        )
        assert deleted_images == 0
        assert deleted_tags == 0
        assert errors == 0  # ValueError is caught and logged as warning, not error


class TestPrintDeletionPlan:
    def test_print_deletion_plan(self) -> None:
        """Test print_deletion_plan with various scenarios."""
        from container_registry_cleanup.logic import DeletionPlan

        now = datetime.now(UTC)
        img1 = ImageVersion("img1", ["dev"], now - timedelta(days=10))
        img2 = ImageVersion("img2", ["v1.0.0", "dev"], now - timedelta(days=10))
        img3 = ImageVersion("img3", ["v2.0.0"], now - timedelta(days=3))
        img4 = ImageVersion("img4", [], now - timedelta(days=10))

        plan = DeletionPlan(
            images_to_delete=[
                (img1, ["dev"], "all_tags_expired"),
                (img4, [], "untagged"),
            ],
            tags_to_delete=[(img2, "dev")],
            tags_to_keep=["v1.0.0", "v2.0.0"],
            tags_in_deleted_images=1,
        )

        # Should not raise any errors
        print_deletion_plan(plan, [img1, img2, img3, img4])
