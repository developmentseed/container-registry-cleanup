import re
from typing import Pattern

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="", case_sensitive=False, extra="allow"
    )

    registry_type: str = ""
    repository_name: str = ""

    version_pattern: str = r"^(v?\d+\.\d+\.\d+.*|latest)$"
    test_pattern: str = r"^pr-\d+$"
    dev_pattern: str = r"^(dev|main|sha-[a-f0-9]+)$"

    test_retention_days: int = 30
    dev_retention_days: int = 7

    dry_run: bool = True

    @field_validator("dry_run", mode="before")
    @classmethod
    def _parse_bool(cls, v: str | bool) -> bool:
        return v if isinstance(v, bool) else v.lower() == "true"

    @property
    def compiled_version_pattern(self) -> Pattern[str]:
        return re.compile(self.version_pattern)

    @property
    def compiled_test_pattern(self) -> Pattern[str]:
        return re.compile(self.test_pattern)

    @property
    def compiled_dev_pattern(self) -> Pattern[str]:
        return re.compile(self.dev_pattern)
