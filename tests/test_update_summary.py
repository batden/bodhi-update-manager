"""Tests for lightweight update-summary helpers."""

from __future__ import annotations

from bodhi_update.models import (
    CONSTRAINT_BLOCKED,
    CONSTRAINT_HELD,
    CONSTRAINT_NORMAL,
    UpdateItem,
    UpdateSummary,
)
from bodhi_update.update_summary import (
    combine_backend_summaries,
    summarize_updates,
)


def make_update(
    name: str,
    *,
    category: str = "system",
    backend: str = "apt",
    constraint: str = CONSTRAINT_NORMAL,
    size: int = 1024,
) -> UpdateItem:
    """Create a minimal UpdateItem for summary tests."""
    return UpdateItem(
        name=name,
        installed_version="1.0",
        candidate_version="2.0",
        size=size,
        origin="test",
        backend=backend,
        category=category,
        description="Test package",
        constraint=constraint,
    )


class FakeSummaryBackend:
    """Backend test double returning a fixed UpdateSummary."""

    def __init__(self, count: int, severity: str) -> None:
        self._summary = UpdateSummary(count=count, severity=severity)

    def get_update_summary(self) -> UpdateSummary:
        return self._summary


class SummaryOnlyBackend:
    """Backend that should be queried through get_update_summary only."""

    def get_update_summary(self) -> UpdateSummary:
        return UpdateSummary(count=3, severity="high")

    def get_updates(self):  # pragma: no cover
        raise AssertionError("summary aggregation should not call get_updates()")


def test_update_summary_defaults() -> None:
    """UpdateSummary should default to no updates and low severity."""
    summary = UpdateSummary()

    assert summary.count == 0
    assert summary.severity == "low"


def test_summarize_updates_empty_list() -> None:
    """An empty update list should summarize to no updates."""
    summary = summarize_updates([])

    assert summary == UpdateSummary(count=0, severity="low")


def test_summarize_updates_counts_normal_updates() -> None:
    """Normal updates should count as actionable."""
    updates = [
        make_update("bash"),
        make_update("coreutils"),
        make_update("moksha"),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 3
    assert summary.severity == "medium"


def test_summarize_updates_ignores_held_and_blocked() -> None:
    """Held and blocked updates should not count as actionable."""
    updates = [
        make_update("normal", constraint=CONSTRAINT_NORMAL),
        make_update("held", constraint=CONSTRAINT_HELD),
        make_update("blocked", constraint=CONSTRAINT_BLOCKED),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 1
    assert summary.severity == "low"


def test_summarize_updates_detects_security_as_high() -> None:
    """Security updates should summarize as high severity."""
    updates = [
        make_update("firefox", category="security"),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 1
    assert summary.severity == "high"


def test_summarize_updates_detects_kernel_as_high() -> None:
    """Kernel updates should summarize as high severity."""
    updates = [
        make_update("linux-image-generic", category="kernel"),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 1
    assert summary.severity == "high"


def test_summarize_updates_detects_medium_apt_packages() -> None:
    """Important APT package prefixes should summarize as medium severity."""
    updates = [
        make_update("systemd"),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 1
    assert summary.severity == "medium"


def test_summarize_updates_low_for_noncritical_packages() -> None:
    """Ordinary system updates should summarize as low severity."""
    updates = [
        make_update("leafpad"),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 1
    assert summary.severity == "low"


def test_summarize_updates_preserves_high_severity() -> None:
    """High severity should not be downgraded by later medium or low updates."""
    updates = [
        make_update("firefox", category="security"),
        make_update("systemd"),
        make_update("leafpad"),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 3
    assert summary.severity == "high"


def test_summarize_updates_preserves_medium_over_low() -> None:
    """Medium severity should not be downgraded by later low updates."""
    updates = [
        make_update("systemd"),
        make_update("leafpad"),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 2
    assert summary.severity == "medium"


def test_summarize_updates_ignores_held_high_severity_update() -> None:
    """Held high-severity updates should not affect count or severity."""
    updates = [
        make_update(
            "firefox",
            category="security",
            constraint=CONSTRAINT_HELD,
        ),
        make_update("leafpad"),
    ]

    summary = summarize_updates(updates)

    assert summary.count == 1
    assert summary.severity == "low"


def test_combine_backend_summaries_empty_list() -> None:
    """No backend summaries should combine to no updates."""
    summary = combine_backend_summaries([])

    assert summary == UpdateSummary(count=0, severity="low")


def test_combine_backend_summaries_counts_all_backends() -> None:
    """Combined summaries should add counts from all backends."""
    backends = [
        FakeSummaryBackend(count=2, severity="low"),
        FakeSummaryBackend(count=3, severity="medium"),
    ]

    summary = combine_backend_summaries(backends)

    assert summary.count == 5
    assert summary.severity == "medium"


def test_combine_backend_summaries_preserves_high_severity() -> None:
    """Combined summaries should preserve high severity."""
    backends = [
        FakeSummaryBackend(count=2, severity="medium"),
        FakeSummaryBackend(count=1, severity="high"),
        FakeSummaryBackend(count=5, severity="low"),
    ]

    summary = combine_backend_summaries(backends)

    assert summary.count == 8
    assert summary.severity == "high"


def test_combine_backend_summaries_preserves_medium_over_low() -> None:
    """Combined summaries should preserve medium severity over low severity."""
    backends = [
        FakeSummaryBackend(count=2, severity="low"),
        FakeSummaryBackend(count=1, severity="medium"),
        FakeSummaryBackend(count=5, severity="low"),
    ]

    summary = combine_backend_summaries(backends)

    assert summary.count == 8
    assert summary.severity == "medium"


def test_combine_backend_summaries_uses_summary_api() -> None:
    """Summary aggregation should use get_update_summary, not get_updates."""
    summary = combine_backend_summaries([SummaryOnlyBackend()])

    assert summary.count == 3
    assert summary.severity == "high"
