"""Tests for small utility helpers."""

from __future__ import annotations

import pytest

from bodhi_update import utils
from bodhi_update.utils import (
    find_privilege_tool,
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


def test_find_privilege_tool_skips_pkexec_when_running_locally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local development runs should skip pkexec and use the next available tool."""
    monkeypatch.setattr(utils.os.path, "abspath", lambda path: "/home/projects/utils.py")

    def fake_which(tool: str) -> str | None:
        if tool in {"pkexec", "sudo"}:
            return f"/usr/bin/{tool}"
        return None

    monkeypatch.setattr(utils.shutil, "which", fake_which)

    assert find_privilege_tool() == "sudo"


def test_find_privilege_tool_allows_pkexec_when_system_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """System-installed runs should prefer pkexec when available."""
    monkeypatch.setattr(
        utils.os.path,
        "abspath",
        lambda path: "/usr/lib/bodhi-update-manager/bodhi_update",
    )

    def fake_which(tool: str) -> str | None:
        if tool == "pkexec":
            return "/usr/bin/pkexec"
        return None

    monkeypatch.setattr(utils.shutil, "which", fake_which)

    assert find_privilege_tool() == "pkexec"


def test_find_privilege_tool_falls_back_to_doas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """doas should be returned if pkexec/sudo are unavailable."""
    monkeypatch.setattr(
        utils.os.path,
        "abspath",
        lambda path: "/usr/lib/bodhi-update-manager/bodhi_update",
    )

    def fake_which(tool: str) -> str | None:
        if tool == "doas":
            return "/usr/bin/doas"
        return None

    monkeypatch.setattr(utils.shutil, "which", fake_which)

    assert find_privilege_tool() == "doas"


def test_find_privilege_tool_returns_none_when_no_tool_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """None should be returned if no supported privilege tool is available."""
    monkeypatch.setattr(
        utils.os.path,
        "abspath",
        lambda path: "/usr/lib/bodhi-update-manager/bodhi_update",
    )
    monkeypatch.setattr(utils.shutil, "which", lambda tool: None)

    assert find_privilege_tool() is None
