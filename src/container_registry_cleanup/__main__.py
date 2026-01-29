import sys

import requests
from loguru import logger

from container_registry_cleanup.logic import (
    create_deletion_plan,
    execute_deletion_plan,
    print_deletion_plan,
)
from container_registry_cleanup.registry import init_registry
from container_registry_cleanup.settings import Settings


def main() -> int:
    settings = Settings()

    # Initialize registry and get all images
    try:
        registry, registry_info = init_registry(settings)
        images = registry.list_images()
    except (ValueError, requests.exceptions.RequestException) as e:
        logger.error(f"Error: {e}")
        return 1

    logger.info(
        f"Registry: {registry_info} | Test={settings.TEST_RETENTION_DAYS}d, "
        f"Dev={settings.DEV_RETENTION_DAYS}d | Dry run: {settings.DRY_RUN}"
    )
    logger.info(f"Found {len(images)} image(s)")

    # Analyze images and create a deletion plan
    plan = create_deletion_plan(images, settings)

    logger.info(
        f"Summary: {len(plan.images_to_delete)} images to delete entirely "
        f"({plan.tags_in_deleted_images} tags), "
        f"{len(plan.tags_to_delete)} individual tags to delete, "
        f"{len(plan.tags_to_keep)} tags to keep"
    )

    # Execute deletions or print dry-run plan
    if settings.DRY_RUN:
        print_deletion_plan(plan, images)
        deleted_images, deleted_tags, errors = 0, 0, 0
    else:
        deleted_images, deleted_tags, errors = execute_deletion_plan(registry, plan)

    registry.write_summary(plan, (deleted_images, deleted_tags, errors), settings)

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
