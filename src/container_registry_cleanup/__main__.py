import sys

import requests
from loguru import logger

from container_registry_cleanup.logic import (
    create_deletion_plan,
    execute_plan,
    write_summary,
)
from container_registry_cleanup.registry import init_registry
from container_registry_cleanup.settings import Settings


def main() -> int:
    settings = Settings()

    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if settings.DEBUG else "INFO")
    logger.info(settings)

    try:
        registry, registry_info = init_registry(settings)
        images = registry.list_images()
    except (ValueError, requests.exceptions.RequestException) as e:
        logger.error(f"Error: {e}")
        return 1

    logger.info(f"Found {len(images)} image(s)")

    plan = create_deletion_plan(images, settings)

    logger.info(
        f"Plan: {len(plan.images_to_delete)} images to delete, "
        f"{len(plan.images_to_keep)} to keep"
    )

    errors = execute_plan(registry, plan, images, settings.DRY_RUN)

    write_summary(plan, errors, settings)

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
