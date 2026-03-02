from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import requests
from loguru import logger
from pydantic import BaseModel

from container_registry_cleanup.base import ImageVersion, RegistryClient
from container_registry_cleanup.settings import Settings


class GHCRSettings(BaseModel):
    GITHUB_TOKEN: str
    GITHUB_REPO_OWNER: str


class GHCRClient(RegistryClient):
    """GitHub Container Registry client.

    Required settings: GITHUB_TOKEN, GITHUB_REPO_OWNER, REPOSITORY_NAME
    Optional settings: GITHUB_STEP_SUMMARY (GitHub Actions step summary file path)
    """

    @classmethod
    def from_settings(cls, settings: Settings) -> GHCRClient:
        import os

        if not settings.REPOSITORY_NAME:
            raise ValueError("Missing required GHCR setting: REPOSITORY_NAME")

        data = {
            **os.environ,
            **{
                k: v
                for k in ["GITHUB_TOKEN", "GITHUB_REPO_OWNER"]
                if (v := getattr(settings, k, None))
            },
        }
        ghcr_settings = GHCRSettings.model_validate(data)
        return cls(
            ghcr_settings.GITHUB_TOKEN,
            ghcr_settings.GITHUB_REPO_OWNER,
            settings.REPOSITORY_NAME,
        )

    def __init__(self, token: str, org_name: str, repository_name: str):
        self.token = token
        self.org_name = org_name
        self.repository_name = repository_name
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def list_images(self) -> list[ImageVersion]:
        all_images: list[ImageVersion] = []
        page = 1

        while True:
            url = f"https://api.github.com/orgs/{self.org_name}/packages/container/{self.repository_name}/versions"
            params: dict[str, str | int] = {
                "page": page,
                "per_page": 100,
                "state": "active",
            }

            response = requests.get(
                url, headers=self.headers, params=params, timeout=30
            )
            response.raise_for_status()

            versions = response.json()
            if not versions:
                break

            for version in versions:
                version_id = str(version.get("id", ""))
                created_at_str = version.get("created_at", "")
                metadata = version.get("metadata", {})
                container_metadata = metadata.get("container", {})
                tags = container_metadata.get("tags", [])

                created_at = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )

                all_images.append(
                    ImageVersion(
                        identifier=version_id,
                        tags=tags,
                        created_at=created_at,
                        metadata={"version": version},
                    )
                )

            page += 1

        self._annotate_oci_references(all_images)
        return all_images

    def delete_image(self, image: ImageVersion) -> None:
        url = f"https://api.github.com/orgs/{self.org_name}/packages/container/{self.repository_name}/versions/{image.identifier}"
        response = requests.delete(url, headers=self.headers, timeout=30)
        response.raise_for_status()

    def delete_tag(self, image: ImageVersion, tag: str) -> None:
        # GHCR REST API can only delete versions (manifests), not individual tags.
        # When a version has multiple tags, deleting it would remove all tags.
        if len(image.tags) > 1:
            other_tags = [t for t in image.tags if t != tag]
            tags_list = ", ".join(other_tags)
            raise ValueError(
                f"Cannot delete tag '{tag}': GHCR's REST API would delete the entire "
                f"image version, removing all tags ({tags_list})"
            )
        self.delete_image(image)

    def _annotate_oci_references(self, images: list[ImageVersion]) -> None:
        """Annotate image metadata with OCI reachability information.

        For every currently tagged digest, recursively traverse registry references and
        mark reachable digests as protected. This prevents deleting untagged manifests
        that are still needed by a tagged OCI index/manifest tree.
        """
        protected_digests: set[str] = set()
        visited: set[str] = set()

        for image in images:
            digest = self._extract_digest_from_version_metadata(image.metadata)
            if digest:
                image.metadata["ghcr_digest"] = digest
            if image.tags and digest:
                self._collect_protected_digests(digest, protected_digests, visited)

        for image in images:
            digest = cast(str | None, image.metadata.get("ghcr_digest"))
            is_protected = bool(digest and digest in protected_digests)
            image.metadata["protected_by_tag_or_index"] = is_protected
            image.metadata["protected_reason"] = (
                "reachable_from_tagged_manifest_or_index"
                if is_protected
                else "not_referenced_by_any_tagged_root"
            )

    def _collect_protected_digests(
        self,
        digest: str,
        protected_digests: set[str],
        visited: set[str],
    ) -> None:
        if digest in visited:
            return

        visited.add(digest)
        protected_digests.add(digest)

        manifest = self._get_manifest(digest)
        if manifest is None:
            return

        media_type = str(manifest.get("mediaType", ""))

        # OCI index / Docker manifest list: recurse into child manifests.
        if self._is_index_media_type(media_type):
            for child in manifest.get("manifests", []) or []:
                child_digest = child.get("digest")
                if isinstance(child_digest, str) and child_digest:
                    self._collect_protected_digests(
                        child_digest, protected_digests, visited
                    )
            return

        # Single manifest: protect config + layers blobs.
        config = manifest.get("config")
        if isinstance(config, dict):
            cfg_digest = config.get("digest")
            if isinstance(cfg_digest, str) and cfg_digest:
                protected_digests.add(cfg_digest)

        for layer in manifest.get("layers", []) or []:
            if isinstance(layer, dict):
                layer_digest = layer.get("digest")
                if isinstance(layer_digest, str) and layer_digest:
                    protected_digests.add(layer_digest)

    def _get_manifest(self, digest: str) -> dict[str, Any] | None:
        """Fetch manifest/index JSON for a digest from GHCR v2 API."""
        url = f"https://ghcr.io/v2/{self.org_name}/{self.repository_name}/manifests/{digest}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": ",".join(
                [
                    "application/vnd.oci.image.index.v1+json",
                    "application/vnd.oci.image.manifest.v1+json",
                    "application/vnd.docker.distribution.manifest.list.v2+json",
                    "application/vnd.docker.distribution.manifest.v2+json",
                ]
            ),
        }
        try:
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, dict) else None
        except requests.exceptions.RequestException:
            logger.warning(
                f"Failed to fetch manifest for {digest[:20]}; "
                "treating as protected to avoid unsafe deletion"
            )
            return None

    @staticmethod
    def _extract_digest_from_version_metadata(metadata: dict[str, Any]) -> str | None:
        """Extract canonical digest (`sha256:...`) from GHCR package version payload."""
        version = metadata.get("version")
        if not isinstance(version, dict):
            return None

        for key in ("name", "digest"):
            value = version.get(key)
            if isinstance(value, str) and value.startswith("sha256:"):
                return value

        container = version.get("metadata", {}).get("container", {})
        if isinstance(container, dict):
            digest_val = container.get("digest")
            if isinstance(digest_val, str) and digest_val.startswith("sha256:"):
                return digest_val

        return None

    @staticmethod
    def _is_index_media_type(media_type: str) -> bool:
        return media_type in {
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
        }
