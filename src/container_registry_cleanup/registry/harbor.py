from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import requests
from dateutil import parser as date_parser  # type: ignore[import-untyped]
from pydantic import BaseModel

from container_registry_cleanup.base import ImageVersion, RegistryClient
from container_registry_cleanup.settings import Settings


class HarborSettings(BaseModel):
    HARBOR_URL: str
    HARBOR_USERNAME: str
    HARBOR_PASSWORD: str
    HARBOR_PROJECT_NAME: str


class HarborClient(RegistryClient):
    """Harbor registry client.

    Required settings:
      HARBOR_URL,
      HARBOR_USERNAME,
      HARBOR_PASSWORD,
      HARBOR_PROJECT_NAME,
      REPOSITORY_NAME
    """

    @classmethod
    def from_settings(cls, settings: Settings) -> HarborClient:
        """Create a HarborClient from settings and environment variables.

        Harbor-specific settings (HARBOR_URL, HARBOR_USERNAME, HARBOR_PASSWORD,
        HARBOR_PROJECT_NAME) are read from environment variables.
        """
        import os

        if not settings.REPOSITORY_NAME:
            raise ValueError("Missing required Harbor setting: REPOSITORY_NAME")

        harbor_settings = HarborSettings.model_validate(os.environ)
        return cls(
            harbor_settings.HARBOR_URL,
            harbor_settings.HARBOR_USERNAME,
            harbor_settings.HARBOR_PASSWORD,
            harbor_settings.HARBOR_PROJECT_NAME,
            settings.REPOSITORY_NAME,
        )

    def __init__(
        self,
        harbor_url: str,
        username: str,
        password: str,
        project_name: str,
        repository_name: str,
    ):
        self.harbor_url = harbor_url.rstrip("/")
        if not self.harbor_url.startswith("http"):
            self.harbor_url = f"https://{self.harbor_url}"
        self.username = username
        self.password = password
        self.project_name = project_name
        self.repository_name = repository_name
        self.auth = (username, password)

    def _get_api_url(self, path: str) -> str:
        return f"{self.harbor_url}/api/v2.0{path}"

    def list_images(self) -> list[ImageVersion]:
        url = self._get_api_url(
            f"/projects/{self.project_name}/repositories/{self.repository_name}/artifacts"
        )
        params: dict[str, Any] = {"page_size": 100, "with_tag": "true"}

        all_images = []
        page = 1

        while True:
            params["page"] = page
            response = requests.get(url, params=params, auth=self.auth, timeout=30)
            response.raise_for_status()

            artifacts = response.json()
            if not artifacts:
                break

            for artifact in artifacts:
                digest = artifact.get("digest", "")
                push_time = artifact.get("push_time")
                tags = artifact.get("tags") or []

                tag_names = [tag.get("name") for tag in tags if tag.get("name")]

                created_at = self._parse_time(push_time)

                all_images.append(
                    ImageVersion(
                        identifier=digest,
                        tags=tag_names,
                        created_at=created_at,
                        metadata={"artifact": artifact},
                    )
                )

            page += 1

        return all_images

    def delete_image(self, image: ImageVersion) -> None:
        url = self._get_api_url(
            f"/projects/{self.project_name}/repositories/{self.repository_name}/artifacts/{image.identifier}"
        )
        response = requests.delete(url, auth=self.auth, timeout=30)
        response.raise_for_status()

    def delete_tag(self, image: ImageVersion, tag: str) -> None:
        url = self._get_api_url(
            f"/projects/{self.project_name}/repositories/{self.repository_name}/artifacts/{image.identifier}/tags/{tag}"
        )
        response = requests.delete(url, auth=self.auth, timeout=30)
        response.raise_for_status()

    @staticmethod
    def _parse_time(time_str: str | datetime) -> datetime:
        parsed = date_parser.parse(time_str) if isinstance(time_str, str) else time_str
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
