"""Tests for Harbor client."""

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from container_registry_cleanup.base import ImageVersion
from container_registry_cleanup.registry import HarborClient
from container_registry_cleanup.settings import Settings


class TestHarborClient:
    def test_from_settings_missing_repository(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HARBOR_URL", "harbor.example.com")
        monkeypatch.setenv("HARBOR_USERNAME", "user")
        monkeypatch.setenv("HARBOR_PASSWORD", "pass")
        monkeypatch.setenv("HARBOR_PROJECT_NAME", "proj")

        settings = Settings()
        settings.REPOSITORY_NAME = ""
        settings.REGISTRY_TYPE = "harbor"
        with pytest.raises(ValueError, match="REPOSITORY_NAME"):
            HarborClient.from_settings(settings)

    def test_from_settings_with_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARBOR_URL", "harbor.example.com")
        monkeypatch.setenv("HARBOR_USERNAME", "user")
        monkeypatch.setenv("HARBOR_PASSWORD", "pass")
        monkeypatch.setenv("HARBOR_PROJECT_NAME", "proj")

        settings = Settings()
        settings.REPOSITORY_NAME = "repo"
        client = HarborClient.from_settings(settings)

        assert client.harbor_url == "https://harbor.example.com"
        assert client.username == "user"
        assert client.password == "pass"
        assert client.project_name == "proj"
        assert client.repository_name == "repo"

    def test_url_normalization(self) -> None:
        client = HarborClient("harbor.example.com", "user", "pass", "proj", "repo")
        assert client.harbor_url == "https://harbor.example.com"

        client2 = HarborClient(
            "https://harbor.example.com", "user", "pass", "proj", "repo"
        )
        assert client2.harbor_url == "https://harbor.example.com"

        client3 = HarborClient(
            "http://harbor.example.com/", "user", "pass", "proj", "repo"
        )
        assert client3.harbor_url == "http://harbor.example.com"

    def test_api_url_construction(self) -> None:
        client = HarborClient("harbor.example.com", "user", "pass", "proj", "repo")
        url = client._get_api_url("/test/path")
        assert url == "https://harbor.example.com/api/v2.0/test/path"

    def test_parse_time_string(self) -> None:
        time_str = "2024-01-01T12:00:00Z"
        parsed = HarborClient._parse_time(time_str)
        assert isinstance(parsed, datetime)
        assert parsed.tzinfo is not None
        offset = parsed.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 0

    def test_parse_time_datetime(self) -> None:
        dt = datetime.now(UTC)
        parsed = HarborClient._parse_time(dt)
        assert parsed == dt

    def test_list_images_single_page(self) -> None:
        client = HarborClient(
            "https://harbor.example.com", "user", "pass", "proj", "repo"
        )

        mock_response_with_data = MagicMock()
        mock_response_with_data.json.return_value = [
            {
                "digest": "sha256:abc123",
                "push_time": "2024-01-01T00:00:00Z",
                "tags": [{"name": "tag1"}, {"name": "tag2"}],
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
        assert images[0].identifier == "sha256:abc123"
        assert images[0].tags == ["tag1", "tag2"]

    def test_list_images_empty_response(self) -> None:
        client = HarborClient(
            "https://harbor.example.com", "user", "pass", "proj", "repo"
        )
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            images = client.list_images()

        assert len(images) == 0

    def test_list_images_empty_tags(self) -> None:
        client = HarborClient(
            "https://harbor.example.com", "user", "pass", "proj", "repo"
        )

        mock_response_with_data = MagicMock()
        mock_response_with_data.json.return_value = [
            {
                "digest": "sha256:abc123",
                "push_time": "2024-01-01T00:00:00Z",
                "tags": None,
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
        assert images[0].tags == []

    def test_delete_image(self) -> None:
        client = HarborClient(
            "https://harbor.example.com", "user", "pass", "proj", "repo"
        )
        image = ImageVersion("sha256:abc123", ["tag1"], datetime.now(UTC))

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.delete", return_value=mock_response) as mock_delete:
            client.delete_image(image)
            mock_delete.assert_called_once()
            call_url = mock_delete.call_args[0][0]
            assert "proj" in call_url
            assert "repo" in call_url
            assert "sha256:abc123" in call_url

    def test_delete_tag(self) -> None:
        client = HarborClient(
            "https://harbor.example.com", "user", "pass", "proj", "repo"
        )
        image = ImageVersion("sha256:abc123", ["tag1", "tag2"], datetime.now(UTC))

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.delete", return_value=mock_response) as mock_delete:
            client.delete_tag(image, "tag1")
            mock_delete.assert_called_once()
            call_url = mock_delete.call_args[0][0]
            assert "tag1" in call_url
