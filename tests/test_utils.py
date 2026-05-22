"""Tests for small utility helpers."""

from __future__ import annotations

import pytest

from bodhi_update import utils
from bodhi_update.utils import (
    format_size,
    get_pkg_severity,
    reboot_required,
)


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [
        (0, "0.0 B"),
        (1, "1.0 B"),
        (1023, "1023.0 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 * 1024 * 1024, "1.0 GB"),
        (1024 * 1024 * 1024 * 1024, "1.0 TB"),
    ],
)
def test_format_size(num_bytes: int, expected: str) -> None:
    """Byte counts should be formatted as human-readable sizes."""
    assert format_size(num_bytes) == expected


def test_reboot_required_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """reboot_required should return True when the reboot marker exists."""
    monkeypatch.setattr(utils.os.path, "exists", lambda path: True)

    assert reboot_required() is True


def test_reboot_required_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """reboot_required should return False when the reboot marker is absent."""
    monkeypatch.setattr(utils.os.path, "exists", lambda path: False)

    assert reboot_required() is False


@pytest.mark.parametrize(
    ("name", "category", "backend", "expected"),
    [
        ("bash", "security", "apt", "high"),
        ("bash", "kernel", "apt", "high"),
        ("linux-image-generic", "system", "apt", "medium"),
        ("systemd", "system", "apt", "medium"),
        ("moksha", "system", "apt", "medium"),
        ("bodhi-update-manager", "system", "apt", "medium"),
        ("firefox", "system", "apt", "low"),
        ("linux-image-generic", "system", "flatpak", "low"),
        ("org.example.App", "system", "flatpak", "low"),
    ],
)
def test_get_pkg_severity(
    name: str,
    category: str,
    backend: str,
    expected: str,
) -> None:
    """Package severity should follow category/backend/name rules."""
    assert get_pkg_severity(name, category, backend) == expected

