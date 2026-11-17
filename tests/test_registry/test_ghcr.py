"""Tests for GHCR client."""

import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from container_registry_cleanup.__main__ import main
from container_registry_cleanup.base import ImageVersion
from container_registry_cleanup.registry import GHCRClient
from container_registry_cleanup.settings import Settings

INDEX = "application/vnd.oci.image.index.v1+json"
LEAF = "application/vnd.oci.image.manifest.v1+json"


def _version(version_id: int, digest: str, tags: list[str]) -> dict[str, Any]:
    return {
        "id": version_id,
        "name": digest,
        "created_at": "2024-01-01T00:00:00Z",
        "metadata": {"container": {"tags": tags}},
    }


# A tagged index with two untagged children, plus an untagged orphan; all are old.
VERSIONS = [
    _version(1, "sha256:index", ["v1.0.0"]),
    _version(2, "sha256:amd64", []),
    _version(3, "sha256:arm64", []),
    _version(4, "sha256:orphan", []),
]
HEALTHY: dict[str, Any] = {
    "sha256:index": {
        "mediaType": INDEX,
        "manifests": [{"digest": "sha256:amd64"}, {"digest": "sha256:arm64"}],
    },
    "sha256:amd64": {"mediaType": LEAF, "layers": []},
    "sha256:arm64": {"mediaType": LEAF, "layers": []},
}
# HEALTHY, but the index also references a digest the registry no longer has.
GONE_CHILD: dict[str, Any] = {
    **HEALTHY,
    "sha256:index": {
        "mediaType": INDEX,
        "manifests": [*HEALTHY["sha256:index"]["manifests"], {"digest": "sha256:gone"}],
    },
}


def _fake_get(
    manifests: dict[str, Any],
    token: Any = None,
    versions: list[dict[str, Any]] = VERSIONS,
) -> Callable[..., requests.Response]:
    """Fake requests.get for the versions API, the token exchange and manifests.

    A token or manifest value that is an exception is raised, an int is the HTTP
    status of an empty response, anything else is a 200 JSON body. Digests missing
    from `manifests` are 404s.
    """

    def reply(value: Any) -> requests.Response:
        if isinstance(value, Exception):
            raise value
        response = requests.Response()
        response.status_code = value if isinstance(value, int) else 200
        response._content = json.dumps(value).encode()
        return response

    def fake_get(url: str, **kwargs: Any) -> requests.Response:
        if url == "https://ghcr.io/token":
            return reply({"token": "registry-jwt"} if token is None else token)
        if url.startswith("https://ghcr.io/v2/org/pkg/manifests/"):
            return reply(manifests.get(url.rsplit("/", 1)[1], 404))
        return reply(versions if kwargs["params"]["page"] == 1 else [])

    return fake_get


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

    def test_get_registry_token_exchanges_github_token(self) -> None:
        """Registry token must be obtained via the ghcr.io/token basic-auth exchange.

        A GITHUB_TOKEN is not a valid bearer token for the ghcr.io distribution API;
        the client must first exchange it for a registry-scoped token at
        https://ghcr.io/token using HTTP Basic auth.
        """
        client = GHCRClient("gh-token", "myorg", "mypackage")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"token": "registry-jwt"}

        with patch("requests.get", return_value=mock_response) as mock_get:
            token = client._get_registry_token()

        assert token == "registry-jwt"
        mock_get.assert_called_once()
        call_args, call_kwargs = mock_get.call_args
        assert call_args[0] == "https://ghcr.io/token"
        assert call_kwargs["params"] == {
            "service": "ghcr.io",
            "scope": "repository:myorg/mypackage:pull",
        }
        assert call_kwargs["auth"] == ("myorg", "gh-token")

    def test_get_registry_token_cached_across_calls(self) -> None:
        """The registry token is fetched once and cached, not re-fetched per manifest."""
        client = GHCRClient("gh-token", "myorg", "mypackage")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"token": "registry-jwt"}

        with patch("requests.get", return_value=mock_response) as mock_get:
            first = client._get_registry_token()
            second = client._get_registry_token()

        assert first == second == "registry-jwt"
        mock_get.assert_called_once()

    def test_get_manifest_performs_two_step_token_exchange_then_fetches(self) -> None:
        """_get_manifest must exchange for a registry token, then use it as Bearer auth.

        This exercises the real HTTP auth path end-to-end (mocked at the requests
        layer) rather than mocking _get_manifest directly, since that is what let
        the original bug (reusing the GitHub API token against ghcr.io/v2/...) ship
        silently: every prior test mocked _get_manifest itself.
        """
        client = GHCRClient("gh-token", "myorg", "mypackage")

        token_response = MagicMock()
        token_response.raise_for_status = MagicMock()
        token_response.json.return_value = {"token": "registry-jwt"}

        manifest_response = MagicMock()
        manifest_response.status_code = 200
        manifest_response.raise_for_status = MagicMock()
        manifest_response.json.return_value = {
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [{"digest": "sha256:child"}],
        }

        def fake_get(url: str, **kwargs: Any) -> MagicMock:
            if url == "https://ghcr.io/token":
                return token_response
            return manifest_response

        with patch("requests.get", side_effect=fake_get) as mock_get:
            manifest = client._get_manifest("sha256:index")

        assert manifest is not None
        assert manifest["manifests"][0]["digest"] == "sha256:child"

        # First call: token exchange. Second call: manifest fetch, authenticated
        # with the exchanged registry token (not the raw GitHub token).
        assert mock_get.call_count == 2
        manifest_call_args, manifest_call_kwargs = mock_get.call_args_list[1]
        assert manifest_call_args[0] == (
            "https://ghcr.io/v2/myorg/mypackage/manifests/sha256:index"
        )
        assert manifest_call_kwargs["headers"]["Authorization"] == "Bearer registry-jwt"

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


class TestFailClosed:
    """If any part of a tagged tree cannot be read, the run must delete nothing."""

    @staticmethod
    def _list(fake_get: Callable[..., requests.Response]) -> list[ImageVersion]:
        with patch("requests.get", side_effect=fake_get):
            return GHCRClient("token", "org", "pkg").list_images()

    @pytest.mark.parametrize(
        "token",
        [requests.ConnectionError("down"), 401, {}],
        ids=["network-error", "http-401", "no-token-in-body"],
    )
    def test_token_failure_raises(self, token: Any) -> None:
        with pytest.raises((requests.RequestException, ValueError)):
            self._list(_fake_get(HEALTHY, token=token))

    @pytest.mark.parametrize(
        "index",
        [requests.ConnectionError("down"), 500, 404, ["not", "an", "object"]],
        ids=["network-error", "http-500", "http-404", "not-an-object"],
    )
    def test_unreadable_tagged_index_raises(self, index: Any) -> None:
        with pytest.raises((requests.RequestException, ValueError)):
            self._list(_fake_get({**HEALTHY, "sha256:index": index}))

    @pytest.mark.parametrize(
        "nested",
        [503, 401, 429, requests.Timeout("slow"), ["not", "an", "object"]],
        ids=["http-503", "http-401", "http-429", "timeout", "not-an-object"],
    )
    def test_unreadable_nested_index_raises(self, nested: Any) -> None:
        """A child index that can't be read hides its own children."""
        manifests = {
            **HEALTHY,
            "sha256:index": {"mediaType": INDEX, "manifests": [{"digest": "sha256:n"}]},
            "sha256:n": nested,
        }
        with pytest.raises((requests.RequestException, ValueError)):
            self._list(_fake_get(manifests))

    def test_listed_child_404_raises(self) -> None:
        """The packages API lists it, so a 404 is not 'gone': its children are unknown."""
        versions = [*VERSIONS, _version(5, "sha256:gone", [])]
        with pytest.raises(ValueError, match="sha256:gone"):
            self._list(_fake_get(GONE_CHILD, versions=versions))

    def test_index_without_media_type_protects_children(self) -> None:
        index = {k: v for k, v in HEALTHY["sha256:index"].items() if k != "mediaType"}
        images = self._list(_fake_get({**HEALTHY, "sha256:index": index}))
        protected = {
            i.identifier: i.metadata["protected_by_tag_or_index"] for i in images
        }
        assert protected == {"1": True, "2": True, "3": True, "4": False}

    def test_missing_child_is_skipped_with_warning(self) -> None:
        """A child that 404s is already gone: warn, keep protecting the rest."""
        warnings: list[str] = []
        sink = logger.add(warnings.append, level="WARNING")
        try:
            images = self._list(_fake_get(GONE_CHILD))
        finally:
            logger.remove(sink)

        protected = {
            i.identifier: i.metadata["protected_by_tag_or_index"] for i in images
        }
        assert protected == {"1": True, "2": True, "3": True, "4": False}
        assert any("sha256:gone" in w for w in warnings)

    def test_tagged_root_404_fails_even_when_first_seen_as_child(self) -> None:
        versions = [*VERSIONS, _version(5, "sha256:gone", ["main"])]
        with pytest.raises(ValueError, match="sha256:gone"):
            self._list(_fake_get(GONE_CHILD, versions=versions))

    @staticmethod
    def _env(monkeypatch: pytest.MonkeyPatch, dry_run: str) -> None:
        for key, value in {
            "REGISTRY_TYPE": "ghcr",
            "GITHUB_TOKEN": "token",
            "GITHUB_REPO_OWNER": "org",
            "REPOSITORY_NAME": "pkg",
            "DRY_RUN": dry_run,
        }.items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    @pytest.mark.parametrize("dry_run", ["false", "true"])
    def test_main_deletes_nothing_and_fails(
        self,
        dry_run: str,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._env(monkeypatch, dry_run)
        broken = _fake_get({**HEALTHY, "sha256:index": 500})
        with (
            patch("requests.get", side_effect=broken),
            patch("requests.delete") as delete,
        ):
            assert main() == 1
        delete.assert_not_called()
        err = capsys.readouterr().err
        assert "nothing will be deleted" in err
        assert "Would delete" not in err

    def test_main_still_deletes_unreferenced_untagged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._env(monkeypatch, "false")
        with (
            patch("requests.get", side_effect=_fake_get(HEALTHY)),
            patch("requests.delete") as delete,
        ):
            assert main() == 0
        delete.assert_called_once()
        assert delete.call_args[0][0].endswith("/versions/4")
