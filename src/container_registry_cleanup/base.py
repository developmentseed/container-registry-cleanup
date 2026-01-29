from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

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
