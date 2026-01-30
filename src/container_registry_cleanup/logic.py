"""Core logic for container registry cleanup."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from re import Pattern
from typing import Any

import requests
from loguru import logger

from container_registry_cleanup.base import ImageVersion, RegistryClient
from container_registry_cleanup.settings import Settings


@dataclass
class ImageDecision:
    """Decision about what to do with an image."""

    image: ImageVersion
    action: str  # "keep" or "delete"
    reason: str
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)


@dataclass
class DeletionPlan:
    decisions: dict[str, ImageDecision]

    @property
    def images_to_delete(self) -> list[tuple[ImageVersion, str]]:
        return [
            (d.image, d.reason) for d in self.decisions.values() if d.action == "delete"
        ]

    @property
    def images_to_keep(self) -> list[tuple[ImageVersion, str]]:
        return [
            (d.image, d.reason) for d in self.decisions.values() if d.action == "keep"
        ]

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


def _get_manifest_info(image: ImageVersion) -> dict[str, Any]:
    """Lazily fetch manifest info if not already cached."""
    if "manifest_info" not in image.metadata:
        registry_client = image.metadata.get("registry_client")
        if registry_client and hasattr(registry_client, "get_manifest_info"):
            image.metadata["manifest_info"] = registry_client.get_manifest_info(image)
        else:
            image.metadata["manifest_info"] = {
                "manifest_type": "unknown",
                "architectures": [],
                "referenced_digests": [],
            }
    manifest_info: dict[str, Any] = image.metadata["manifest_info"]
    return manifest_info


def _decide_action(
    image: ImageVersion,
    settings: Settings,
    child_to_parent: dict[str, str],
) -> tuple[str, str]:
    """Decide whether to keep or delete an image.

    Returns:
        - action: "keep" or "delete"
        - reason: explanation
    """
    if not image.tags:
        # Untagged image - check if orphaned
        manifest_info = _get_manifest_info(image)
        is_single_arch = manifest_info.get("manifest_type") == "manifest"
        img_digest = image.identifier.replace("sha256:", "")
        has_parent = img_digest in child_to_parent

        if is_single_arch and not has_parent:
            return "delete", "orphaned manifest (no parent)"

        should_delete, reason = _evaluate_untagged(
            image.created_at, settings.OTHERS_RETENTION_DAYS
        )
        # Annotate child manifests with parent
        if has_parent and not should_delete:
            reason = f"{reason} (parent: {child_to_parent[img_digest]})"

        return ("delete" if should_delete else "keep"), (
            "untagged" if should_delete else reason
        )

    # Tagged image - evaluate all tags
    tag_decisions = [
        _evaluate_tag(
            tag,
            image.created_at,
            settings.OTHERS_RETENTION_DAYS,
            settings.TEST_RETENTION_DAYS,
            settings.compiled_version_pattern,
            settings.compiled_test_pattern,
        )
        for tag in image.tags
    ]

    has_tag_to_keep = any(not should_delete for should_delete, _ in tag_decisions)

    if has_tag_to_keep:
        return "keep", "has_tags_to_keep"
    else:
        return "delete", "all_tags_expired"


def _get_short_id(identifier: str) -> str:
    """Get short ID from identifier."""
    return identifier[:12] if len(identifier) > 12 else identifier


def create_deletion_plan(
    images: list[ImageVersion], settings: Settings
) -> DeletionPlan:
    decisions: dict[str, ImageDecision] = {}
    child_to_parent: dict[str, str] = {}
    parent_to_children: dict[str, list[str]] = {}

    # Pass 1: Decide fate + discover relationships
    for image in images:
        img_id = _get_short_id(image.identifier)
        img_digest = image.identifier.replace("sha256:", "")

        # Discover parent-child relationships (only tagged images can be parents)
        if image.tags:
            manifest_info = _get_manifest_info(image)
            if manifest_info.get("manifest_type") == "manifest_list":
                children = manifest_info.get("referenced_digests", [])
                parent_to_children[img_id] = children
                for child_digest in children:
                    child_to_parent[child_digest] = img_id

        # Decide action
        action, reason = _decide_action(image, settings, child_to_parent)

        decisions[img_id] = ImageDecision(
            image=image,
            action=action,
            reason=reason,
        )

        # Log decision
        _log_decision(img_id, image, action, reason, settings)

    # Pass 2: Wire up relationships
    for img_id, decision in decisions.items():
        img_digest = decision.image.identifier.replace("sha256:", "")
        decision.parent_id = child_to_parent.get(img_digest)
        decision.child_ids = parent_to_children.get(img_id, [])

    return DeletionPlan(decisions)


def _log_decision(
    img_id: str,
    image: ImageVersion,
    action: str,
    reason: str,
    settings: Settings,
) -> None:
    """Log the decision made for an image."""
    if not image.tags:
        if action == "delete":
            if "orphaned" in reason:
                logger.info(f"ORPHANED: DELETE - {reason}")
            else:
                logger.info(f"UNTAGGED: DELETE - {reason}")
            logger.debug(f"[{img_id}] DELETE: {reason}")
        else:
            logger.debug(f"[{img_id}] KEEP: {reason}")
    else:
        # Log individual tag decisions for tagged images
        for tag in image.tags:
            should_delete, tag_reason = _evaluate_tag(
                tag,
                image.created_at,
                settings.OTHERS_RETENTION_DAYS,
                settings.TEST_RETENTION_DAYS,
                settings.compiled_version_pattern,
                settings.compiled_test_pattern,
            )
            logger.debug(
                f"[{img_id}] tag '{tag}': {'DELETE' if should_delete else 'KEEP'} - {tag_reason}"
            )
        logger.debug(
            f"[{img_id}] {'DELETE' if action == 'delete' else 'KEEP'}: {reason}"
        )


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

    def format_manifest_info(img: ImageVersion) -> str:
        """Format manifest type info for display."""
        manifest_info = _get_manifest_info(img)
        manifest_type = manifest_info.get("manifest_type")
        architectures = manifest_info.get("architectures", [])
        if manifest_type == "manifest_list" and architectures:
            return f" [multi-arch: {', '.join(architectures)}]"
        elif manifest_type == "manifest":
            return " [single-arch]"
        return ""

    deleted_images = len(plan.images_to_delete)
    deleted_tags = plan.count_deleted_tags()
    action = "Deleted" if not settings.DRY_RUN else "To delete"
    kept_action = "Kept" if not settings.DRY_RUN else "To keep"
    mode = "Dry Run" if settings.DRY_RUN else "Live"

    with open(settings.GITHUB_STEP_SUMMARY, "w") as f:
        f.write(
            f"### Container Image Cleanup\n\n"
            f"| Metric | Count |\n"
            f"|--------|-------|\n"
            f"| Images: kept | {len(plan.images_to_keep)} |\n"
            f"| Images: deleted | {deleted_images} |\n"
            f"| Errors | {errors} |\n\n"
            f"**Mode:** {mode} | "
            f"**Retention:** Test={settings.TEST_RETENTION_DAYS}d, "
            f"Others={settings.OTHERS_RETENTION_DAYS}d\n\n"
        )

        if plan.images_to_delete:
            f.write(f"**{action}: {deleted_images} images ({deleted_tags} tags)**\n\n")
            f.write("| Image ID | Tags | Type | Reason |\n")
            f.write("|----------|------|------|--------|\n")
            for img, reason in plan.images_to_delete:
                img_id = (
                    img.identifier[:12] if len(img.identifier) > 12 else img.identifier
                )
                tags_str = ", ".join(img.tags) if img.tags else "untagged"
                type_info = format_manifest_info(img).strip()
                f.write(f"| `{img_id}` | {tags_str} | {type_info} | {reason} |\n")
            f.write("\n")

        if plan.images_to_keep:
            f.write(
                f"**{kept_action}: {len(plan.images_to_keep)} images ({plan.count_kept_tags()} tags)**\n\n"
            )
            f.write("| Image ID | Tags | Type | Reason |\n")
            f.write("|----------|------|------|--------|\n")
            for img, reason in plan.images_to_keep:
                img_id = (
                    img.identifier[:12] if len(img.identifier) > 12 else img.identifier
                )
                tags_str = ", ".join(img.tags) if img.tags else "untagged"
                type_info = format_manifest_info(img).strip()
                f.write(f"| `{img_id}` | {tags_str} | {type_info} | {reason} |\n")
