"""Helpers for lightweight update summaries."""

import logging
from collections.abc import Iterable

from bodhi_update.models import CONSTRAINT_NORMAL, UpdateItem, UpdateSummary
from bodhi_update.utils import get_pkg_severity

log = logging.getLogger("bodhi-update-manager")

_SUMMARY_ERRORS = (
    ImportError,
    OSError,
    RuntimeError,
    ValueError,
    AttributeError,
    TypeError,
)


def summarize_updates(updates: list[UpdateItem]) -> UpdateSummary:
    """Return count/severity summary for actionable updates."""
    count = 0
    severity = "low"

    for update in updates:
        if getattr(update, "constraint", CONSTRAINT_NORMAL) != CONSTRAINT_NORMAL:
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


def combine_backend_summaries(backends: Iterable[object]) -> UpdateSummary:
    """Combine update summaries from multiple backends.

    Broken/unavailable backends are skipped so one plugin cannot prevent the
    tray/status summary from updating for the remaining backends.
    """
    count = 0
    severity = "low"

    for backend in backends:
        backend_id = getattr(backend, "backend_id", backend.__class__.__name__)

        try:
            summary = backend.get_update_summary()
        except _SUMMARY_ERRORS:
            log.exception("Backend %s skipped while combining summaries", backend_id)
            continue

        count += summary.count

        if summary.severity == "high":
            severity = "high"
        elif summary.severity == "medium" and severity != "high":
            severity = "medium"

    return UpdateSummary(count=count, severity=severity)
