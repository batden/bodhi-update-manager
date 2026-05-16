"""Tests for APT backend helper functions."""

from __future__ import annotations

import subprocess

from bodhi_update.models import (
    CONSTRAINT_BLOCKED,
    CONSTRAINT_HELD,
    CONSTRAINT_NORMAL,
)
from bodhi_update.plugins.apt import (
    AptBackend,
    _determine_category,
    _is_kernel_update,
    _is_security_update,
    _output_mentions_network_error,
    _stderr_mentions_lock,
)


def test_is_security_update_detects_security_origin() -> None:
    """Origins containing 'security' should be classified as security updates."""
    assert _is_security_update("jammy-security")
    assert _is_security_update("bookworm-security")
    assert _is_security_update("Ubuntu Security")


def test_is_security_update_rejects_normal_origin() -> None:
    """Normal archive origins should not be classified as security updates."""
    assert not _is_security_update("jammy-updates")
    assert not _is_security_update("bookworm")
    assert not _is_security_update("unknown")


def test_is_kernel_update_detects_common_kernel_packages() -> None:
    """Common Linux kernel package names should be classified as kernel updates."""
    assert _is_kernel_update("linux-image-generic")
    assert _is_kernel_update("linux-headers-generic")
    assert _is_kernel_update("linux-modules-6.8.0-31-generic")


def test_is_kernel_update_rejects_non_kernel_packages() -> None:
    """Non-kernel package names should not be classified as kernel updates."""
    assert not _is_kernel_update("bash")
    assert not _is_kernel_update("libgtk-3-0")
    assert not _is_kernel_update("moksha")


def test_determine_category_prefers_security_over_kernel() -> None:
    """Security origin should win even for kernel packages."""
    category = _determine_category("linux-image-generic", "jammy-security")

    assert category == "security"


def test_determine_category_kernel() -> None:
    """Kernel package names should be categorized as kernel updates."""
    category = _determine_category("linux-image-generic", "jammy-updates")

    assert category == "kernel"


def test_determine_category_system() -> None:
    """Ordinary packages should be categorized as system updates."""
    category = _determine_category("bash", "jammy-updates")

    assert category == "system"

def test_security_origin_marks_package_security() -> None:
    assert _determine_category("nano", "jammy-security") == "security"

def test_determine_category_internel_security_policy() -> None:
    """Firefox package should be categorized as security update."""
    category = _determine_category("firefox", "jammy-updates")

    assert category == "security"

def test_stderr_mentions_lock_detects_common_lock_errors() -> None:
    """APT/dpkg lock messages should be detected."""
    assert _stderr_mentions_lock("Could not get lock /var/lib/dpkg/lock-frontend")
    assert _stderr_mentions_lock("Unable to acquire the dpkg frontend lock")
    assert _stderr_mentions_lock("Unable to lock directory /var/lib/apt/lists/")


def test_stderr_mentions_lock_rejects_unrelated_errors() -> None:
    """Unrelated stderr should not be treated as a lock conflict."""
    assert not _stderr_mentions_lock("Temporary failure resolving archive.ubuntu.com")
    assert not _stderr_mentions_lock("Package has no installation candidate")


def test_output_mentions_network_error_detects_dns_failure() -> None:
    """DNS/network failures should be detected from apt output."""
    assert _output_mentions_network_error("Temporary failure in name resolution")
    assert _output_mentions_network_error("Could not resolve archive.ubuntu.com")


def test_output_mentions_network_error_detects_fetch_failure() -> None:
    """APT fetch failures should be detected from apt output."""
    assert _output_mentions_network_error("Failed to fetch http://example.invalid")
    assert _output_mentions_network_error("Some index files failed to download")


def test_output_mentions_network_error_rejects_unrelated_output() -> None:
    """Unrelated output should not be treated as a network error."""
    assert not _output_mentions_network_error("Reading package lists... Done")
    assert not _output_mentions_network_error("Package lists refreshed.")


def test_parse_refresh_output_success() -> None:
    """A zero return code should be interpreted as successful refresh."""
    result = subprocess.CompletedProcess(
        args=["apt-get", "update"],
        returncode=0,
        stdout="Hit:1 http://example.invalid stable InRelease\n",
        stderr="",
    )

    success, message = AptBackend._parse_refresh_output(result)

    assert success is True
    assert "refreshed" in message.lower()


def test_parse_refresh_output_network_error() -> None:
    """Network-like apt output should produce a friendly network error."""
    result = subprocess.CompletedProcess(
        args=["apt-get", "update"],
        returncode=100,
        stdout="",
        stderr="Temporary failure in name resolution",
    )

    success, message = AptBackend._parse_refresh_output(result)

    assert success is False
    assert "internet connection" in message.lower()


def test_parse_refresh_output_lock_error() -> None:
    """APT lock errors should produce a package-manager-busy message."""
    result = subprocess.CompletedProcess(
        args=["apt-get", "update"],
        returncode=100,
        stdout="",
        stderr="Could not get lock /var/lib/dpkg/lock-frontend",
    )

    success, message = AptBackend._parse_refresh_output(result)

    assert success is False
    assert "package manager" in message.lower()
    assert "running" in message.lower()


def test_parse_refresh_output_generic_error_uses_first_stderr_line() -> None:
    """Generic refresh failures should include the first useful stderr line."""
    result = subprocess.CompletedProcess(
        args=["apt-get", "update"],
        returncode=100,
        stdout="",
        stderr="\nSomething went wrong\nMore details\n",
    )

    success, message = AptBackend._parse_refresh_output(result)

    assert success is False
    assert "Something went wrong" in message


def test_classify_constraint_held_package() -> None:
    """Held packages should be marked as held."""
    constraint, description = AptBackend._classify_constraint(
        "bash",
        "GNU Bourne Again SHell",
        {"bash"},
        set(),
    )

    assert constraint == CONSTRAINT_HELD
    assert description == "GNU Bourne Again SHell"


def test_classify_constraint_blocked_package() -> None:
    """Kept-back packages should be marked as blocked by dependency constraints."""
    constraint, description = AptBackend._classify_constraint(
        "libfoo",
        "Library foo",
        set(),
        {"libfoo"},
    )

    assert constraint == CONSTRAINT_BLOCKED
    assert "blocked" in description.lower()


def test_classify_constraint_normal_package() -> None:
    """Packages that are neither held nor kept back should be normal."""
    constraint, description = AptBackend._classify_constraint(
        "bash",
        "GNU Bourne Again SHell",
        set(),
        set(),
    )

    assert constraint == CONSTRAINT_NORMAL
    assert description == "GNU Bourne Again SHell"


def test_classify_constraint_held_takes_priority_over_blocked() -> None:
    """If a package appears in both sets, held should take priority."""
    constraint, description = AptBackend._classify_constraint(
        "bash",
        "GNU Bourne Again SHell",
        {"bash"},
        {"bash"},
    )

    assert constraint == CONSTRAINT_HELD
    assert description == "GNU Bourne Again SHell"

def test_user_security_policy_marks_package_security(monkeypatch) -> None:
    monkeypatch.setattr(
        "bodhi_update.plugins.apt.is_user_security_package",
        lambda name: name == "my-browser",
    )

    assert _determine_category("my-browser", "jammy") == "security"
    assert _determine_category("nano", "jammy") == "system"
