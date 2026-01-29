"""Core logic for container registry cleanup."""

from dataclasses import dataclass
from datetime import UTC, datetime
from re import Pattern

import requests
from loguru import logger

from container_registry_cleanup.base import ImageVersion, RegistryClient
from container_registry_cleanup.settings import Settings


@dataclass
class DeletionPlan:
    images_to_delete: list[tuple[ImageVersion, list[str], str]]
    tags_to_delete: list[tuple[ImageVersion, str]]
    tags_to_keep: list[str]
    tags_in_deleted_images: int


def _evaluate_tag(
    tag_name: str,
    created_at: datetime,
    others_retention_days: int,
    test_retention_days: int,
    version_pattern: Pattern[str],
    test_pattern: Pattern[str],
) -> tuple[bool, str]:
    """Determine if a tag should be deleted. Returns (should_delete, reason)."""
    age_days = (datetime.now(UTC) - created_at).days

    if version_pattern.match(tag_name):
        return False, f"version tag (protected, {age_days}d old)"

    if test_pattern.match(tag_name):
        if test_retention_days == 0:
            return True, f"test tag (retention=0d, {age_days}d old)"
        return (
            age_days > test_retention_days,
            f"test tag >{test_retention_days}d ({age_days}d old)",
        )

    if others_retention_days == 0:
        return True, f"other tag (retention=0d, {age_days}d old)"
    return (
        age_days > others_retention_days,
        f"other tag >{others_retention_days}d ({age_days}d old)",
    )


def _evaluate_untagged(
    created_at: datetime, others_retention_days: int
) -> tuple[bool, str]:
    """Determine if an untagged image should be deleted. Returns (should_delete, reason)."""
    age_days = (datetime.now(UTC) - created_at).days
    if others_retention_days == 0:
        return True, f"untagged (retention=0d, {age_days}d old)"
    return (
        age_days > others_retention_days,
        f"untagged >{others_retention_days}d ({age_days}d old)",
    )


def create_deletion_plan(
    images: list[ImageVersion], settings: Settings
) -> DeletionPlan:
    version_pattern = settings.compiled_version_pattern
    test_pattern = settings.compiled_test_pattern
    plan = DeletionPlan(
        images_to_delete=[],
        tags_to_delete=[],
        tags_to_keep=[],
        tags_in_deleted_images=0,
    )

    for image in images:
        if not image.tags:
            should_delete, reason = _evaluate_untagged(
                image.created_at, settings.OTHERS_RETENTION_DAYS
            )
            if should_delete:
                logger.info(f"UNTAGGED: DELETE - {reason}")
                plan.images_to_delete.append((image, [], "untagged"))
            continue

        tags_to_delete = []
        tags_to_keep = []

        for tag in image.tags:
            should_delete, reason = _evaluate_tag(
                tag,
                image.created_at,
                settings.OTHERS_RETENTION_DAYS,
                settings.TEST_RETENTION_DAYS,
                version_pattern,
                test_pattern,
            )
            if should_delete:
                logger.info(f"{tag}: DELETE - {reason}")
                tags_to_delete.append(tag)
            else:
                tags_to_keep.append(tag)
                plan.tags_to_keep.append(tag)

        if tags_to_delete and not tags_to_keep:
            plan.images_to_delete.append((image, tags_to_delete, "all_tags_expired"))
            plan.tags_in_deleted_images += len(tags_to_delete)
        elif tags_to_delete:
            for tag in tags_to_delete:
                plan.tags_to_delete.append((image, tag))

    return plan


def print_deletion_plan(plan: DeletionPlan, images: list[ImageVersion]) -> None:
    deleted_image_ids = {img.identifier for img, _, _ in plan.images_to_delete}
    tags_to_keep_set = set(plan.tags_to_keep)

    # Images to delete
    if plan.images_to_delete:
        logger.info("Images to delete")
        for image, tag_names, reason in plan.images_to_delete:
            if reason == "untagged":
                logger.info(f"  - {image.identifier[:20]}... (untagged)")
            else:
                tags_str = ", ".join(tag_names)
                logger.info(f"  - {image.identifier[:20]}... ({tags_str})")

    # Tags to delete (individual tags from images that aren't being deleted entirely)
    if plan.tags_to_delete:
        logger.info("Tags to delete")
        for image, tag in plan.tags_to_delete:
            if image.identifier not in deleted_image_ids:
                logger.info(f"  - {tag} (image: {image.identifier[:20]}...)")

    # Images to keep
    images_to_keep: list[tuple[ImageVersion, list[str] | None]] = []
    for image in images:
        if image.identifier not in deleted_image_ids:
            if not image.tags:
                # Untagged image that's not being deleted
                images_to_keep.append((image, None))
            else:
                # Image with tags - check if any tags are being kept
                kept_tags = [tag for tag in image.tags if tag in tags_to_keep_set]
                if kept_tags:
                    images_to_keep.append((image, kept_tags))

    if images_to_keep:
        logger.info("Images to keep")
        for image, kept_tags_or_none in images_to_keep:
            if kept_tags_or_none is None:
                logger.info(f"  - {image.identifier[:20]}... (untagged)")
            else:
                tags_str = ", ".join(kept_tags_or_none)
                logger.info(f"  - {image.identifier[:20]}... ({tags_str})")


def execute_deletion_plan(
    registry: RegistryClient, plan: DeletionPlan
) -> tuple[int, int, int]:
    if not plan.tags_to_delete and not plan.images_to_delete:
        logger.info("No tags or images to delete")
        return 0, 0, 0

    logger.info("PERFORMING DELETIONS...")
    deleted_images = deleted_tags = errors = 0
    image_ids = {img.identifier for img, _, _ in plan.images_to_delete}

    for image, tag_names, reason in plan.images_to_delete:
        try:
            registry.delete_image(image)
            deleted_images += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Error deleting image {image.identifier[:20]}...: {e}")
            errors += 1

    processed_images = set(image_ids)
    for image, tag_name in plan.tags_to_delete:
        if image.identifier not in processed_images:
            try:
                registry.delete_tag(image, tag_name)
                deleted_tags += 1
            except ValueError as e:
                logger.warning(f"Cannot delete tag '{tag_name}'. {e}. Skipping.")
            except requests.exceptions.RequestException as e:
                logger.error(f"Error deleting tag {tag_name}: {e}")
                errors += 1

    logger.info(
        f"Deleted: {deleted_images} images, {deleted_tags} tags, {errors} errors"
    )
    return deleted_images, deleted_tags, errors
