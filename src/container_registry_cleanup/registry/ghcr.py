from __future__ import annotations

from datetime import datetime

import requests
from pydantic import BaseModel

from container_registry_cleanup.base import ImageVersion, RegistryClient
from container_registry_cleanup.logic import DeletionPlan
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
        all_images = []
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

    def write_summary(
        self, plan: DeletionPlan, stats: tuple[int, int, int], settings: Settings
    ) -> None:
        """Write cleanup summary to GitHub Actions step summary file."""
        github_step_summary = getattr(settings, "GITHUB_STEP_SUMMARY", None)
        if not github_step_summary:
            return
        deleted_images, deleted_tags, errors = stats
        with open(github_step_summary, "w") as f:
            f.write("### Container Image Cleanup\n\n")
            f.write("| Metric | Count |\n|--------|-------|\n")
            f.write(f"| Kept | {len(plan.tags_to_keep)} |\n")
            f.write(f"| Deleted (images) | {deleted_images} |\n")
            f.write(f"| Deleted (tags) | {deleted_tags} |\n")
            f.write(f"| Errors | {errors} |\n\n")
            f.write(f"**Mode:** {'Dry Run' if settings.DRY_RUN else 'Live'} | ")
            f.write(
                f"**Retention:** Test={settings.TEST_RETENTION_DAYS}d, Others={settings.OTHERS_RETENTION_DAYS}d\n"
            )
