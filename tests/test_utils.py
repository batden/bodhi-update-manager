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

def test_find_pkexec_returns_shutil_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """find_pkexec should return the path reported by shutil.which."""
    monkeypatch.setattr(utils.shutil, "which", lambda name: "/usr/bin/pkexec")

    assert utils.find_pkexec() == "/usr/bin/pkexec"


def test_find_pkexec_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """find_pkexec should return None when pkexec is unavailable."""
    monkeypatch.setattr(utils.shutil, "which", lambda name: None)

    assert utils.find_pkexec() is None


def test_require_pkexec_returns_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """require_pkexec should return the pkexec path when available."""
    monkeypatch.setattr(utils, "find_pkexec", lambda: "/usr/bin/pkexec")

    assert utils.require_pkexec() == "/usr/bin/pkexec"


def test_require_pkexec_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """require_pkexec should raise RuntimeError when pkexec is unavailable."""
    monkeypatch.setattr(utils, "find_pkexec", lambda: None)

    with pytest.raises(RuntimeError, match="pkexec is required"):
        utils.require_pkexec()

def test_validate_deb_files_accepts_deb_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_deb_files should return normalized paths for .deb files."""
    deb_file = tmp_path / "example.deb"
    deb_file.write_bytes(b"fake deb content")

    monkeypatch.setattr(utils, "magic", None)

    assert utils.validate_deb_files([str(deb_file)]) == [str(deb_file.resolve())]

def test_validate_deb_files_rejects_missing_file(tmp_path) -> None:
    """validate_deb_files should reject missing files."""
    missing = tmp_path / "missing.deb"

    with pytest.raises(FileNotFoundError, match="File not found"):
        utils.validate_deb_files([str(missing)])


def test_validate_deb_files_rejects_non_deb_file(tmp_path) -> None:
    """validate_deb_files should reject files without a .deb suffix."""
    txt_file = tmp_path / "example.txt"
    txt_file.write_text("not a deb", encoding="utf-8")

    with pytest.raises(ValueError, match="Not a Debian package"):
        utils.validate_deb_files([str(txt_file)])

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

