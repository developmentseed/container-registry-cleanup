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
    images_to_delete: list[tuple[ImageVersion, str]]
    images_to_keep: list[tuple[ImageVersion, str]]

    def count_kept_tags(self) -> int:
        """Count tags in images that are being kept."""
        return sum(len(img.tags) for img, _ in self.images_to_keep)

    def count_deleted_tags(self) -> int:
        """Count tags in images being deleted."""
        return sum(len(img.tags) for img, _ in self.images_to_delete)


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
    plan = DeletionPlan(images_to_delete=[], images_to_keep=[])

    for image in images:
        img_id = (
            image.identifier[:12] if len(image.identifier) > 12 else image.identifier
        )

        if not image.tags:
            should_delete, reason = _evaluate_untagged(
                image.created_at, settings.OTHERS_RETENTION_DAYS
            )
            if should_delete:
                logger.info(f"UNTAGGED: DELETE - {reason}")
                logger.debug(f"[{img_id}] DELETE: {reason}")
                plan.images_to_delete.append((image, "untagged"))
            else:
                logger.debug(f"[{img_id}] KEEP: {reason}")
                plan.images_to_keep.append((image, reason))
            continue

        tag_decisions = []
        for tag in image.tags:
            should_delete, reason = _evaluate_tag(
                tag,
                image.created_at,
                settings.OTHERS_RETENTION_DAYS,
                settings.TEST_RETENTION_DAYS,
                version_pattern,
                test_pattern,
            )
            tag_decisions.append((tag, should_delete, reason))
            logger.debug(
                f"[{img_id}] tag '{tag}': {'DELETE' if should_delete else 'KEEP'} - {reason}"
            )

        has_tag_to_keep = any(
            not should_delete for _, should_delete, _ in tag_decisions
        )

        if has_tag_to_keep:
            logger.debug(f"[{img_id}] KEEP: has_tags_to_keep")
            plan.images_to_keep.append((image, "has_tags_to_keep"))
        else:
            logger.debug(f"[{img_id}] DELETE: all_tags_expired")
            plan.images_to_delete.append((image, "all_tags_expired"))

    return plan


def execute_plan(
    registry: RegistryClient,
    plan: DeletionPlan,
    images: list[ImageVersion],
    dry_run: bool,
) -> int:
    if not plan.images_to_delete:
        logger.info("No images to delete")
        return 0

    if dry_run:
        logger.info(f"DRY RUN: Would delete {len(plan.images_to_delete)} images")
        return 0

    logger.info("PERFORMING DELETIONS...")
    deleted = errors = 0

    for image, reason in plan.images_to_delete:
        try:
            registry.delete_image(image)
            deleted += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"Error deleting image {image.identifier[:20]}...: {e}")
            errors += 1

    logger.info(f"Deleted: {deleted} images, {errors} errors")
    return errors


def write_summary(plan: DeletionPlan, errors: int, settings: Settings) -> None:
    """Write cleanup summary to GitHub Actions step summary."""
    if not settings.GITHUB_STEP_SUMMARY:
        return

    deleted_images = len(plan.images_to_delete)
    deleted_tags = plan.count_deleted_tags()
    action = "To Delete" if settings.DRY_RUN else "Deleted"
    mode = "Dry Run" if settings.DRY_RUN else "Live"

    with open(settings.GITHUB_STEP_SUMMARY, "w") as f:
        f.write(
            f"### Container Image Cleanup\n\n"
            f"| Metric | Count |\n"
            f"|--------|-------|\n"
            f"| Kept | {plan.count_kept_tags()} |\n"
            f"| {action} (images) | {deleted_images} |\n"
            f"| {action} (tags) | {deleted_tags} |\n"
            f"| Errors | {errors} |\n\n"
            f"**Mode:** {mode} | "
            f"**Retention:** Test={settings.TEST_RETENTION_DAYS}d, "
            f"Others={settings.OTHERS_RETENTION_DAYS}d\n\n"
        )

        if plan.images_to_delete:
            f.write(
                f"<details>\n<summary>{action}: {len(plan.images_to_delete)} images ({plan.count_deleted_tags()} tags)</summary>\n\n"
            )
            for img, reason in plan.images_to_delete:
                img_id = (
                    img.identifier[:12] if len(img.identifier) > 12 else img.identifier
                )
                tags_str = ", ".join(img.tags) if img.tags else "untagged"
                f.write(f"- `{img_id}` — {tags_str} — _{reason}_\n")
            f.write("\n</details>\n\n")

        if plan.images_to_keep:
            f.write(
                f"<details>\n<summary>Kept: {len(plan.images_to_keep)} images ({plan.count_kept_tags()} tags)</summary>\n\n"
            )
            for img, reason in plan.images_to_keep:
                img_id = (
                    img.identifier[:12] if len(img.identifier) > 12 else img.identifier
                )
                tags_str = ", ".join(img.tags) if img.tags else "untagged"
                f.write(f"- `{img_id}` — {tags_str} — _{reason}_\n")
            f.write("\n</details>\n")
