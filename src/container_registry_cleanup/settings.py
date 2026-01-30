import re
from typing import Pattern

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    REGISTRY_TYPE: str = ""
    REPOSITORY_NAME: str = ""

    VERSION_PATTERN: str = r"^(v?\d+\.\d+\.\d+.*|latest)$"
    TEST_PATTERN: str = r"^pr-\d+$"

    TEST_RETENTION_DAYS: int = 30
    OTHERS_RETENTION_DAYS: int = 7

    DRY_RUN: bool = True
    DEBUG: bool = False
    GITHUB_STEP_SUMMARY: str | None = None

    @field_validator("DRY_RUN", "DEBUG", mode="before")
    @classmethod
    def _parse_bool(cls, v: str | bool) -> bool:
        return v if isinstance(v, bool) else v.lower() == "true"

    @property
    def compiled_version_pattern(self) -> Pattern[str]:
        return re.compile(self.VERSION_PATTERN)

    @property
    def compiled_test_pattern(self) -> Pattern[str]:
        return re.compile(self.TEST_PATTERN)
