from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from container_registry_cleanup.logic import DeletionPlan
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

    def write_summary(
        self, plan: DeletionPlan, stats: tuple[int, int, int], settings: Settings
    ) -> None:
        """Write cleanup summary to GitHub Actions step summary."""
        if not settings.GITHUB_STEP_SUMMARY:
            return

        deleted_images, deleted_tags, errors = stats
        action = "To Delete" if settings.DRY_RUN else "Deleted"
        mode = "Dry Run" if settings.DRY_RUN else "Live"

        with open(settings.GITHUB_STEP_SUMMARY, "w") as f:
            f.write(
                f"### Container Image Cleanup\n\n"
                f"| Metric | Count |\n"
                f"|--------|-------|\n"
                f"| Kept | {len(plan.tags_to_keep)} |\n"
                f"| {action} (images) | {deleted_images} |\n"
                f"| {action} (tags) | {deleted_tags} |\n"
                f"| Errors | {errors} |\n\n"
                f"**Mode:** {mode} | "
                f"**Retention:** Test={settings.TEST_RETENTION_DAYS}d, "
                f"Others={settings.OTHERS_RETENTION_DAYS}d\n"
            )
