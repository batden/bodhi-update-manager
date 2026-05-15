"""Helpers for lightweight update summaries."""

from bodhi_update.models import CONSTRAINT_NORMAL, UpdateItem, UpdateSummary
from bodhi_update.utils import get_pkg_severity


def summarize_updates(updates: list[UpdateItem]) -> UpdateSummary:
    """Return count/severity summary for actionable updates."""
    count = 0
    severity = "low"

    for update in updates:
        if getattr(update, "constraint",
                   CONSTRAINT_NORMAL) != CONSTRAINT_NORMAL:
            continue

        count += 1

        pkg_severity = get_pkg_severity(
            update.name,
            update.category,
            update.backend,
        )

        if pkg_severity == "high":
            severity = "high"
        elif pkg_severity == "medium" and severity != "high":
            severity = "medium"

    return UpdateSummary(count=count, severity=severity)
