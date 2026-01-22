"""Tests for base module."""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from container_registry_cleanup.base import ImageVersion


class TestImageVersion:
    def test_image_version_creation(self) -> None:
        created = datetime.now(UTC)
        image = ImageVersion("digest123", ["tag1", "tag2"], created)
        assert image.identifier == "digest123"
        assert image.tags == ["tag1", "tag2"]
        assert image.created_at == created
        assert image.metadata == {}

    def test_image_version_with_metadata(self) -> None:
        image = ImageVersion("digest123", ["tag1"], datetime.now(UTC), {"key": "value"})
        assert image.metadata == {"key": "value"}
