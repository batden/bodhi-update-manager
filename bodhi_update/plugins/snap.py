"""Snap-backed update discovery for the Bodhi Update Manager."""

from __future__ import annotations

import shutil
import subprocess
import time

from bodhi_update.backends import BackendMeta, UpdateBackend, _API
from bodhi_update.models import (
    CONSTRAINT_HELD,
    CONSTRAINT_NORMAL,
    UpdateItem,
    UpdateSummary,
)
from bodhi_update.security_policy import is_user_security_package
from bodhi_update.utils import require_pkexec

_SNAP_HELPER = "/usr/libexec/um-actions-snap"

class SnapBackend(UpdateBackend):
    """Update backend that queries installed Snap packages."""

    meta = BackendMeta(
        backend_id="snap",
        display_name="Snap Packages",
        API=_API,
        filter_group="snap",
        filter_label="Snap",
        filter_sort_order=200,
        show_in_preferences=True,
        icon_name="package-x-generic-symbolic",
    )

    # Fallback cache TTL used when `snap refresh --time` is unavailable or
    # unparsable. Snapd normally refreshes on its own schedule, so there is no
    # need to run the heavier `snap refresh --list` on every tray poll.
    _SUMMARY_FALLBACK_TTL = 60 * 60

    def __init__(self) -> None:
        self._summary = UpdateSummary()
        self._last_refresh_stamp: str | None = None
        self._last_summary_check = 0.0

    def is_available(self) -> bool:
        """Return True only if snap exists and snapd is responsive.

        Uses `snap list` as a lightweight probe: it requires no network access
        and succeeds as long as snapd is running.  A non-zero exit, timeout,
        or OSError is treated as unavailable.
        """
        if shutil.which("snap") is None:
            return False
        try:
            result = subprocess.run(
                ["snap", "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=8,
                check=False,
            )
            if result.returncode != 0:
                return False
            # Paranoia: stderr containing daemon-unavailable text is a hard fail.
            stderr_text = (result.stderr or
                           b"").decode(errors="replace").lower()
            return "cannot connect" not in stderr_text
        except (OSError, subprocess.TimeoutExpired):
            return False

    def check_busy(self) -> tuple[bool, str]:
        """Return False because Snap locking is handled by snapd."""
        return False, ""

    def refresh(self) -> tuple[bool, str]:
        """No-op refresh; Snap update discovery is queried live."""
        return True, ""

    def supports_hold(self) -> bool:
        return True

    def build_hold_command(self, package: str, hold: bool) -> list[str]:
        action = "hold" if hold else "unhold"
        return [require_pkexec(), _SNAP_HELPER, action, package]
    
    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_snap_table(stdout: str) -> list[list[str]]:
        """Return non-header, non-blank rows from a snap tabular output."""
        rows: list[list[str]] = []
        for line in stdout.strip().splitlines():
            stripped = line.strip()
            if not stripped or stripped.lower().startswith("name"):
                continue
            parts = stripped.split()
            if parts:
                rows.append(parts)
        return rows

    @staticmethod
    def _refresh_time_stamp() -> str | None:
        """Return snapd's last refresh timestamp, or None if unavailable.

        `snap refresh --time` is used as a cheap signal.  If the reported
        "last:" value has not changed, the cached summary is still valid.
        """
        try:
            result = subprocess.run(
                ["snap", "refresh", "--time"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0 or not result.stdout:
            return None

        for line in result.stdout.splitlines():
            if line.lower().startswith("last:"):
                return line.partition(":")[2].strip()

        return None

    def _installed_info(self) -> dict[str, tuple[str, bool]]:
        """Return {snap_name: (installed_version, is_held)} from `snap list`.

        snap list columns:
          Name  Version  Rev  Tracking  Publisher  Notes

        The Notes column can contain values such as:
          -
          classic
          held
          classic,held
        """
        try:
            result = subprocess.run(
                ["snap", "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}

        if result.returncode != 0 or not result.stdout:
            return {}

        installed: dict[str, tuple[str, bool]] = {}

        for row in self._parse_snap_table(result.stdout):
            if len(row) < 2:
                continue

            name = row[0]
            version = row[1]
            notes = row[5] if len(row) >= 6 else ""

            note_tokens = {
                token.strip().lower()
                for token in notes.split(",")
                if token.strip()
            }
            is_held = "held" in note_tokens

            installed[name] = (version, is_held)

        return installed

    def _query_pending_refreshes(self) -> str:
        """Return stdout from `snap refresh --list`, or an empty string."""
        try:
            result = subprocess.run(
                ["snap", "refresh", "--list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""

        return result.stdout or ""

    # ------------------------------------------------------------------ #
    # Backend interface                                                    #
    # ------------------------------------------------------------------ #

    def get_update_summary(self) -> UpdateSummary:
        """Return a cached lightweight summary of pending Snap refreshes.

        Tray polling only needs count/severity.  Avoid the heavier get_updates()
        path because it also calls `snap list` and builds UpdateItem objects.

        The summary is refreshed when snapd's reported last refresh time changes.
        If that timestamp cannot be read, fall back to a time-based cache.
        """
        now = time.monotonic()
        stamp = self._refresh_time_stamp()

        if stamp is not None and stamp == self._last_refresh_stamp:
            return self._summary

        if stamp is None and (
                now - self._last_summary_check < self._SUMMARY_FALLBACK_TTL):
            return self._summary

        stdout = self._query_pending_refreshes()
        if stdout.strip():
            self._summary = UpdateSummary(
                count=len(self._parse_snap_table(stdout)),
                severity="low",
            )
        else:
            self._summary = UpdateSummary()

        self._last_refresh_stamp = stamp
        self._last_summary_check = now
        return self._summary

    def get_updates(self) -> tuple[list[UpdateItem], int]:
        """Return snaps that have an available refresh.

        `snap refresh --list` reports only snaps with a pending update; it does
        NOT list all installed snaps, so no filtering is needed.
        Installed versions are looked up separately from `snap list`.
        """
        stdout = self._query_pending_refreshes()
        if not stdout.strip():
            return [], 0

        installed = self._installed_info()

        updates: list[UpdateItem] = []
        # snap refresh --list columns: Name  Version  Rev  Size  Publisher  Notes
        for row in self._parse_snap_table(stdout):
            if len(row) < 2:
                continue
            name = row[0]
            candidate_version = row[1]
            installed_version, is_held = installed.get(name, ("-", False))
            constraint = CONSTRAINT_HELD if is_held else CONSTRAINT_NORMAL

            category = "security" if is_user_security_package(name) else "snap"
            description = "Held Snap package" if is_held else "Snap package"

            updates.append(
                UpdateItem(
                    name=name,
                    installed_version=installed_version,
                    candidate_version=candidate_version,
                    size=0,
                    origin="snap",
                    backend="snap",
                    category=category,
                    description=description,
                    constraint=constraint,
                )
            )

        return updates, 0

    def build_install_command(self,
                              packages: list[str] | None = None) -> list[str]:
        """Return argv to refresh selected Snap packages.

        If *packages* is None or empty, discover all pending Snap refreshes and
        return a command for those snaps.  The returned argv is passed directly to
        VTE spawn_async; no shell quoting or wrapping is performed.
        """
        if not packages:
            discovered, _ = self.get_updates()
            packages = [item.name for item in discovered]
        if not packages:
            return ["true"]  # nothing to refresh; exit cleanly
        return [require_pkexec(), _SNAP_HELPER, "refresh", *packages]
