"""Tests for GHCR client."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from container_registry_cleanup.base import ImageVersion
from container_registry_cleanup.registry import GHCRClient
from container_registry_cleanup.settings import Settings


class TestGHCRClient:
    def test_from_settings_missing_repository(self) -> None:
        """Test from_settings raises error when REPOSITORY_NAME is missing."""
        settings = Settings()
        settings.REPOSITORY_NAME = ""  # Explicitly set to empty
        settings.REGISTRY_TYPE = "ghcr"
        with pytest.raises(ValueError, match="REPOSITORY_NAME"):
            GHCRClient.from_settings(settings)

    def test_from_settings_with_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test from_settings reads from environment variables."""
        monkeypatch.setenv("GITHUB_TOKEN", "env-token")
        monkeypatch.setenv("GITHUB_REPO_OWNER", "env-org")

        settings = Settings()
        settings.REPOSITORY_NAME = "test-repo"
        client = GHCRClient.from_settings(settings)

        assert client.token == "env-token"
        assert client.org_name == "env-org"
        assert client.repository_name == "test-repo"

    def test_from_settings_with_github_repo_owner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test from_settings reads GITHUB_REPO_OWNER."""
        monkeypatch.setenv("GITHUB_TOKEN", "token")
        monkeypatch.setenv("GITHUB_REPO_OWNER", "alt-org")

        settings = Settings()
        settings.REPOSITORY_NAME = "test-repo"
        client = GHCRClient.from_settings(settings)

        assert client.token == "token"
        assert client.org_name == "alt-org"

    def test_headers_setup(self) -> None:
        client = GHCRClient("token123", "myorg", "mypackage")
        assert "Bearer token123" in client.headers["Authorization"]
        assert client.headers["Accept"] == "application/vnd.github+json"
        assert client.headers["X-GitHub-Api-Version"] == "2022-11-28"
        assert client.org_name == "myorg"
        assert client.repository_name == "mypackage"

    def test_list_images_single_page(self) -> None:
        """Test list_images with single page response."""
        client = GHCRClient("token", "org", "pkg")

        # First call returns data, second call returns empty to break pagination loop
        mock_response_with_data = MagicMock()
        mock_response_with_data.json.return_value = [
            {
                "id": 123,
                "created_at": "2024-01-01T00:00:00Z",
                "metadata": {"container": {"tags": ["tag1", "tag2"]}},
            }
        ]
        mock_response_with_data.raise_for_status = MagicMock()

        mock_response_empty = MagicMock()
        mock_response_empty.json.return_value = []
        mock_response_empty.raise_for_status = MagicMock()

        with patch(
            "requests.get", side_effect=[mock_response_with_data, mock_response_empty]
        ):
            images = client.list_images()

        assert len(images) == 1
        assert images[0].identifier == "123"
        assert images[0].tags == ["tag1", "tag2"]

    def test_list_images_empty_response(self) -> None:
        """Test list_images with empty response."""
        client = GHCRClient("token", "org", "pkg")
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            images = client.list_images()

        assert len(images) == 0

    def test_delete_image(self) -> None:
        """Test delete_image makes correct API call."""
        client = GHCRClient("token", "org", "pkg")
        image = ImageVersion("img123", ["tag1"], datetime.now(UTC))

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.delete", return_value=mock_response) as mock_delete:
            client.delete_image(image)
            mock_delete.assert_called_once()
            call_url = mock_delete.call_args[0][0]
            assert "org" in call_url
            assert "pkg" in call_url
            assert "img123" in call_url

    def test_delete_tag_with_multiple_tags_raises_error(self) -> None:
        """GHCR REST API can only delete versions (manifests), not individual tags.

        When a version has multiple tags, deleting it would remove all tags.
        This implementation prevents accidental deletion of other tags.
        """
        client = GHCRClient("token", "org", "pkg")
        image = ImageVersion("digest1", ["tag1", "tag2"], datetime.now(UTC))

        with pytest.raises(ValueError, match="GHCR's REST API would delete the entire"):
            client.delete_tag(image, "tag1")

    def test_delete_tag_with_single_tag(self) -> None:
        """GHCR can delete tag when it's the only tag."""
        client = GHCRClient("token", "org", "pkg")
        image = ImageVersion("digest1", ["tag1"], datetime.now(UTC))

        with patch.object(client, "delete_image") as mock_delete:
            client.delete_tag(image, "tag1")
            mock_delete.assert_called_once_with(image)

    def test_annotate_oci_references_tagged_index_protects_untagged_children(
        self,
    ) -> None:
        """Tagged OCI index should protect referenced untagged child manifests."""
        client = GHCRClient("token", "org", "pkg")
        now = datetime.now(UTC)

        tagged_index = ImageVersion(
            "id-index",
            ["titiler-openeo-v0.12.0"],
            now,
            metadata={"version": {"name": "sha256:index"}},
        )
        untagged_child_amd64 = ImageVersion(
            "id-amd64",
            [],
            now,
            metadata={"version": {"name": "sha256:amd64"}},
        )
        untagged_child_arm64 = ImageVersion(
            "id-arm64",
            [],
            now,
            metadata={"version": {"name": "sha256:arm64"}},
        )

        manifest_map: dict[str, dict[str, Any]] = {
            "sha256:index": {
                "mediaType": "application/vnd.oci.image.index.v1+json",
                "manifests": [
                    {"digest": "sha256:amd64"},
                    {"digest": "sha256:arm64"},
                ],
            },
            "sha256:amd64": {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {"digest": "sha256:cfg-amd64"},
                "layers": [{"digest": "sha256:layer-amd64"}],
            },
            "sha256:arm64": {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {"digest": "sha256:cfg-arm64"},
                "layers": [{"digest": "sha256:layer-arm64"}],
            },
        }

        with patch.object(
            client, "_get_manifest", side_effect=lambda d: manifest_map.get(d)
        ):
            client._annotate_oci_references(
                [tagged_index, untagged_child_amd64, untagged_child_arm64]
            )

        assert tagged_index.metadata["protected_by_tag_or_index"] is True
        assert (
            tagged_index.metadata["protected_reason"]
            == "reachable_from_tagged_manifest_or_index"
        )
        assert untagged_child_amd64.metadata["protected_by_tag_or_index"] is True
        assert untagged_child_arm64.metadata["protected_by_tag_or_index"] is True

    def test_annotate_oci_references_multi_platform_and_orphan_digest(self) -> None:
        """Multi-platform tagged index protects referenced manifests, not orphan digest."""
        client = GHCRClient("token", "org", "pkg")
        now = datetime.now(UTC)

        tagged_multi = ImageVersion(
            "id-multi",
            ["v1.2.3"],
            now,
            metadata={"version": {"name": "sha256:multi-index"}},
        )
        amd64_manifest = ImageVersion(
            "id-linux-amd64",
            [],
            now,
            metadata={"version": {"name": "sha256:linux-amd64"}},
        )
        arm64_manifest = ImageVersion(
            "id-linux-arm64",
            [],
            now,
            metadata={"version": {"name": "sha256:linux-arm64"}},
        )
        orphan_digest = ImageVersion(
            "id-orphan",
            [],
            now,
            metadata={"version": {"name": "sha256:orphan"}},
        )

        manifest_map: dict[str, dict[str, Any]] = {
            "sha256:multi-index": {
                "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
                "manifests": [
                    {"digest": "sha256:linux-amd64"},
                    {"digest": "sha256:linux-arm64"},
                ],
            },
            "sha256:linux-amd64": {
                "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "config": {"digest": "sha256:cfg-linux-amd64"},
                "layers": [{"digest": "sha256:layer-linux-amd64"}],
            },
            "sha256:linux-arm64": {
                "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "config": {"digest": "sha256:cfg-linux-arm64"},
                "layers": [{"digest": "sha256:layer-linux-arm64"}],
            },
        }

        with patch.object(
            client, "_get_manifest", side_effect=lambda d: manifest_map.get(d)
        ):
            client._annotate_oci_references(
                [tagged_multi, amd64_manifest, arm64_manifest, orphan_digest]
            )

        assert tagged_multi.metadata["protected_by_tag_or_index"] is True
        assert amd64_manifest.metadata["protected_by_tag_or_index"] is True
        assert arm64_manifest.metadata["protected_by_tag_or_index"] is True
        assert orphan_digest.metadata["protected_by_tag_or_index"] is False
        assert (
            orphan_digest.metadata["protected_reason"]
            == "not_referenced_by_any_tagged_root"
        )
