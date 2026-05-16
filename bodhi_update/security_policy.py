"""User-defined security package policy."""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path

APP_NAME = "bodhi-update-manager"
log = logging.getLogger(APP_NAME)

DEFAULT_SECURITY_PATTERNS = (
    "firefox",
    "firefox-esr",
    "chromium*",
    "google-chrome*",
    "brave-browser",
    "vivaldi*",
    "librewolf*",
    "thunderbird",
    "openssh*",
)

_SECURITY_PATTERNS: tuple[str, ...] | None = None


def get_security_policy_path() -> Path:
    """Return the user security policy config path."""
    config_home = os.environ.get(
        "XDG_CONFIG_HOME",
        os.path.expanduser("~/.config"),
    )
    return Path(config_home) / APP_NAME / "security-packages.conf"


def load_security_patterns() -> tuple[str, ...]:
    """Return built-in and user-defined security package patterns.

    The config file is line based. Blank lines and comments are ignored.
    Patterns use shell-style matching, for example:

        firefox
        chromium*
        openssh*
    """
    patterns = list(DEFAULT_SECURITY_PATTERNS)
    path = get_security_policy_path()

    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()

                if not stripped or stripped.startswith("#"):
                    continue

                patterns.append(stripped)
    except FileNotFoundError:
        pass
    except OSError as exc:
        log.warning("Could not read security policy file %s: %s", path, exc)

    return tuple(dict.fromkeys(patterns))


def get_security_patterns() -> tuple[str, ...]:
    """Return cached built-in and user-defined security package patterns."""
    global _SECURITY_PATTERNS

    if _SECURITY_PATTERNS is None:
        _SECURITY_PATTERNS = load_security_patterns()

    return _SECURITY_PATTERNS


def reload_security_patterns() -> tuple[str, ...]:
    """Reload security patterns from disk and return the updated cache.

    This is mostly useful for tests or future UI support. Normal app usage can
    rely on the cache being loaded once per process.
    """
    global _SECURITY_PATTERNS

    _SECURITY_PATTERNS = load_security_patterns()
    return _SECURITY_PATTERNS


def is_user_security_package(package_name: str) -> bool:
    """Return True if package_name matches the user security policy."""
    return any(
        fnmatch.fnmatchcase(package_name, pattern)
        for pattern in get_security_patterns()
    )
