from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

import requests
from loguru import logger

if TYPE_CHECKING:
    from container_registry_cleanup.settings import Settings


@dataclass
class ImageVersion:
    """Container image version/artifact.

    It standardizes image data across different registry implementations so the cleanup logic
    can work with a single structure.
    """

    identifier: str
    tags: list[str]
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


def fetch_manifest_info(
    url: str,
    headers: dict[str, str],
    image_id: str,
    auth: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch and parse manifest information from Docker Registry V2 API.

    Returns dict with:
    - manifest_type: "manifest_list", "manifest", or "unknown"
    - architectures: list of architectures (if manifest_list)
    - media_type: the manifest media type
    - referenced_digests: list of digests referenced by manifest list (if manifest_list)
    """
    accept_types = [
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
    ]
    headers = {**headers, "Accept": ", ".join(accept_types)}

    try:
        response = requests.get(url, headers=headers, auth=auth, timeout=30)
        response.raise_for_status()
        manifest = response.json()
        media_type = manifest.get("mediaType", response.headers.get("Content-Type", ""))

        if "manifest.list" in media_type or "image.index" in media_type:
            manifests = manifest.get("manifests", [])
            architectures = [
                m.get("platform", {}).get("architecture")
                for m in manifests
                if m.get("platform", {}).get("architecture")
            ]
            # Extract digests of referenced manifests
            referenced_digests = [
                m.get("digest", "").replace("sha256:", "")
                for m in manifests
                if m.get("digest")
            ]
            return {
                "manifest_type": "manifest_list",
                "architectures": architectures,
                "media_type": media_type,
                "referenced_digests": referenced_digests,
            }
        else:
            return {
                "manifest_type": "manifest",
                "architectures": [],
                "media_type": media_type,
            }
    except Exception as e:
        logger.debug(f"Could not fetch manifest info for image {image_id[:12]}: {e}")
        return {
            "manifest_type": "unknown",
            "architectures": [],
            "media_type": "",
            "referenced_digests": [],
        }


class RegistryClient(ABC):
    """Abstract base class for registry implementations."""

    @classmethod
    @abstractmethod
    def from_settings(cls, settings: Settings) -> RegistryClient:
        pass

    @abstractmethod
    def list_images(self) -> list[ImageVersion]:
        pass

    @abstractmethod
    def delete_image(self, image: ImageVersion) -> None:
        pass

    @abstractmethod
    def delete_tag(self, image: ImageVersion, tag: str) -> None:
        pass
