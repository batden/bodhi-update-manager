"""Tests for APT backend lightweight update summaries."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bodhi_update.models import (
    CONSTRAINT_BLOCKED,
    CONSTRAINT_HELD,
    CONSTRAINT_NORMAL,
    UpdateItem,
    UpdateSummary,
)
from bodhi_update.plugins import apt
from bodhi_update.plugins.apt import AptBackend


def make_update(
    name: str,
    *,
    category: str = "system",
    backend: str = "apt",
    constraint: str = CONSTRAINT_NORMAL,
    size: int = 1024,
) -> UpdateItem:
    """Create a minimal UpdateItem for APT summary tests."""
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


def test_apt_get_update_summary_defaults() -> None:
    """A new AptBackend should start with an empty cached summary."""
    backend = AptBackend()

    assert backend._summary_stamp is None  # pylint: disable=protected-access
    assert backend._summary == UpdateSummary()  # pylint: disable=protected-access


def test_apt_get_update_summary_builds_summary_on_first_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first summary call should read updates and cache the result."""
    backend = AptBackend()

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: (100.0, 200.0))
    monkeypatch.setattr(
        backend,
        "get_updates",
        lambda: ([make_update("leafpad")], 1024),
    )

    summary = backend.get_update_summary()

    assert summary == UpdateSummary(count=1, severity="low")
    assert backend._summary_stamp == (100.0, 200.0)  # pylint: disable=protected-access
    assert backend._summary == summary  # pylint: disable=protected-access


def test_apt_get_update_summary_reuses_cache_when_stamp_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APT summary should reuse cached data when APT/dpkg state is unchanged."""
    backend = AptBackend()
    calls = 0

    def fake_get_updates() -> tuple[list[UpdateItem], int]:
        nonlocal calls
        calls += 1
        return [make_update("bash")], 1024

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: (100.0, 200.0))
    monkeypatch.setattr(backend, "get_updates", fake_get_updates)

    first = backend.get_update_summary()
    second = backend.get_update_summary()

    assert first == UpdateSummary(count=1, severity="medium")
    assert second == first
    assert calls == 1


def test_apt_get_update_summary_reloads_when_stamp_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APT summary should reload when APT/dpkg state changes."""
    backend = AptBackend()
    calls = 0
    stamps: Iterator[tuple[float, float]] = iter([
        (100.0, 200.0),
        (101.0, 200.0),
    ])

    def fake_get_updates() -> tuple[list[UpdateItem], int]:
        nonlocal calls
        calls += 1
        return [make_update(f"pkg-{calls}")], 1024

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: next(stamps))
    monkeypatch.setattr(backend, "get_updates", fake_get_updates)

    first = backend.get_update_summary()
    second = backend.get_update_summary()

    assert first == UpdateSummary(count=1, severity="low")
    assert second == UpdateSummary(count=1, severity="low")
    assert calls == 2


def test_apt_get_update_summary_updates_cached_value_when_stamp_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A changed stamp should replace the cached summary value."""
    backend = AptBackend()
    stamps: Iterator[tuple[float, float]] = iter([
        (100.0, 200.0),
        (101.0, 200.0),
    ])
    update_sets: Iterator[list[UpdateItem]] = iter([
        [make_update("leafpad")],
        [
            make_update("firefox", category="security"),
            make_update("bash"),
        ],
    ])

    def fake_get_updates() -> tuple[list[UpdateItem], int]:
        return next(update_sets), 1024

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: next(stamps))
    monkeypatch.setattr(backend, "get_updates", fake_get_updates)

    first = backend.get_update_summary()
    second = backend.get_update_summary()

    assert first == UpdateSummary(count=1, severity="low")
    assert second == UpdateSummary(count=2, severity="high")
    assert backend._summary == second  # pylint: disable=protected-access


def test_apt_get_update_summary_ignores_held_and_blocked_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Held and blocked updates should not count in the tray summary."""
    backend = AptBackend()

    updates = [
        make_update("normal", constraint=CONSTRAINT_NORMAL),
        make_update("held", constraint=CONSTRAINT_HELD),
        make_update("blocked", constraint=CONSTRAINT_BLOCKED),
    ]

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: (100.0, 200.0))
    monkeypatch.setattr(backend, "get_updates", lambda: (updates, 1024))

    summary = backend.get_update_summary()

    assert summary == UpdateSummary(count=1, severity="low")


def test_apt_get_update_summary_preserves_high_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High severity should not be downgraded by medium or low updates."""
    backend = AptBackend()

    updates = [
        make_update("firefox", category="security"),
        make_update("systemd"),
        make_update("leafpad"),
    ]

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: (100.0, 200.0))
    monkeypatch.setattr(backend, "get_updates", lambda: (updates, 1024))

    summary = backend.get_update_summary()

    assert summary == UpdateSummary(count=3, severity="high")


def test_apt_get_update_summary_preserves_medium_over_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Medium severity should not be downgraded by low updates."""
    backend = AptBackend()

    updates = [
        make_update("systemd"),
        make_update("leafpad"),
    ]

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: (100.0, 200.0))
    monkeypatch.setattr(backend, "get_updates", lambda: (updates, 1024))

    summary = backend.get_update_summary()

    assert summary == UpdateSummary(count=2, severity="medium")


def test_apt_get_update_summary_does_not_use_total_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary generation should use update count/severity, not total bytes."""
    backend = AptBackend()

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: (100.0, 200.0))
    monkeypatch.setattr(
        backend,
        "get_updates",
        lambda: ([make_update("leafpad")], 999999999),
    )

    summary = backend.get_update_summary()

    assert summary == UpdateSummary(count=1, severity="low")


def test_apt_get_update_summary_cached_result_avoids_get_updates_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once cached, unchanged APT state should avoid the expensive update path."""
    backend = AptBackend()
    calls = 0

    def fake_get_updates() -> tuple[list[UpdateItem], int]:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("get_updates should not be called again")
        return [make_update("leafpad")], 1024

    monkeypatch.setattr(apt, "_apt_state_stamp", lambda: (100.0, 200.0))
    monkeypatch.setattr(backend, "get_updates", fake_get_updates)

    first = backend.get_update_summary()
    second = backend.get_update_summary()

    assert first == second
    assert calls == 1
