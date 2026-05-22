"""Small utility helpers for display, system state checks, and severity classification."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

APP_NAME = "bodhi-update-manager"
log = logging.getLogger(APP_NAME)

try:
    import magic  # Suggested but optional
except ImportError:
    log.debug("Magic module is unavailable")
    magic = None


_SYSTEM_PREFIX = "/usr/lib/"
REBOOT_REQUIRED_PATH = "/var/run/reboot-required"

def find_pkexec() -> str | None:
    """Return pkexec path if available, else None."""
    return shutil.which("pkexec")


def require_pkexec() -> str:
    """Return pkexec path or raise RuntimeError."""
    pkexec = find_pkexec()
    if pkexec is None:
        log.debug("pkexec is unavailable")
        raise RuntimeError("pkexec is required but was not found.")
    return pkexec


def format_size(num_bytes: int) -> str:
    """Convert a size in bytes into a human-readable string (e.g. 23.5 MB)."""
    size = float(num_bytes)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"  # unreachable, but satisfies the type checker


def reboot_required() -> bool:
    """Return True if the system has flagged that a restart is needed."""
    return os.path.exists(REBOOT_REQUIRED_PATH)


# Keep this list small: core platform plumbing only.
_MEDIUM_PREFIXES = (
    "linux-",
    "systemd",
    "libc",
    "glibc",
    "dbus",
    "openssl",
    "gnupg",
    "apt",
    "dpkg",
    "bash",
    "coreutils",
    "util-linux",
    "sudo",
    "moksha",
    "bodhi-",
)


def get_pkg_severity(name: str, category: str, backend: str) -> str:
    """Return high, medium, or low severity for an update item."""
    if category in ("security", "kernel"):
        return "high"
    if backend == "apt" and name.startswith(_MEDIUM_PREFIXES):
        return "medium"
    return "low"


def validate_deb_files(deb_files: list[str]) -> list[str]:
    """Validate Debian package paths and return normalized paths."""
    validated: list[str] = []

    for deb in deb_files:
        path = Path(deb).expanduser().resolve()
        log.debug("Deb file path: %s", path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {deb}")

        if not path.is_file():
            raise ValueError(f"Not a regular file: {deb}")

        if path.suffix.lower() != ".deb":
            raise ValueError(f"Not a Debian package: {deb}")

        if magic is not None:
            file_type = magic.from_file(str(path), mime=True)
            if file_type != "application/vnd.debian.binary-package":
                raise ValueError(f"APT cannot open: {deb}")

        validated.append(str(path))

    return validated
