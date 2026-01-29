from __future__ import annotations

from container_registry_cleanup.base import ImageVersion, RegistryClient
from container_registry_cleanup.settings import Settings

from .ghcr import GHCRClient

__all__ = [
    "ImageVersion",
    "RegistryClient",
    "GHCRClient",
    "init_registry",
]


def init_registry(settings: Settings) -> tuple[RegistryClient, str]:
    registry_type = settings.REGISTRY_TYPE.lower()
    registries: dict[str, type[RegistryClient]] = {
        "ghcr": GHCRClient,
    }
    if registry_type not in registries:
        raise ValueError(
            f"REGISTRY_TYPE must be one of {list(registries.keys())}, got '{registry_type}'"
        )
    registry_class = registries[registry_type]
    registry = registry_class.from_settings(settings)
    # Get the organization/project name from the registry instance
    if isinstance(registry, GHCRClient):
        org_or_project = registry.org_name
    else:
        org_or_project = None
    info = f"{registry_type.upper()}: {org_or_project}/{settings.REPOSITORY_NAME}"
    return registry, info
