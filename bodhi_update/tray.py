"""Integrated tray indicator for the Update Manager.

Owns one tray icon per application instance. Actions lazily create the
UpdateManagerWindow via get_or_create_window() — the window is not
pre-created in tray mode, so GTK can't implicitly show it at startup.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import TYPE_CHECKING

import gi

from bodhi_update.backends import get_registry, initialize_registry
from bodhi_update.models import CONSTRAINT_BLOCKED, CONSTRAINT_HELD
from bodhi_update.utils import get_pkg_severity

gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")

# ---------------------------------------------------------------------------
# AppIndicator backend detection (must come after gi.require_version calls)
# ---------------------------------------------------------------------------

try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as appindicator
except (ValueError, ImportError):
    # fall back to AppIndicator
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as appindicator

from gi.repository import GLib, Gtk  # noqa: E402

if TYPE_CHECKING:
    from bodhi_update.app import UpdateManagerApplication

APP_NAME = "bodhi-update-manager"
log = logging.getLogger(APP_NAME)


def _read_pref(key: str, default: bool = True) -> bool:
    """Read a single boolean preference from the shared prefs file."""
    config_home = os.environ.get("XDG_CONFIG_HOME",
                                 os.path.expanduser("~/.config"))
    path = os.path.join(config_home, APP_NAME, "prefs.json")

    try:
        with open(path, encoding="utf-8") as config:
            data = json.load(config)
            if isinstance(data, dict):
                return bool(data.get(key, default))
    except (OSError, json.JSONDecodeError, AttributeError):
        # File missing, bad JSON, or non-dict data.
        pass

    return default

# ---------------------------------------------------------------------------
# Tray implementation
# ---------------------------------------------------------------------------


class TrayIcon:
    """System-tray icon that operates on the application window.

    Receives the application object (not the window) so the window can be
    created lazily on first use.  Call :meth:`destroy` when the app exits.
    """

    _ICON_NAME = "bodhi-update-manager"
    _ICON_SIZE = 22  # px — standard system-tray icon size

    _ICON_BY_SEVERITY: dict[str, str] = {
        "low":    "notification_cyan",
        "medium": "notification_amber",
        "high":   "notification_red",
    }

    # Background poll interval (seconds).
    _POLL_INTERVAL = 15 * 60  # 15 minutes
    _INITIAL_DELAY = 5  # seconds after startup before first check

    def __init__(self, app: UpdateManagerApplication) -> None:
        """Initialise the tray icon and schedule the first background poll."""
        self._app = app
        self._indicator = None
        self._poll_running: bool = False
        self._poll_source_id: int | None = None
        self._last_count: int = 0  # most recent count from set_update_count
        self._shown: bool = False

        menu = self._build_menu()

        self._indicator = appindicator.Indicator.new(
            self._ICON_NAME,
            self._ICON_NAME,
            appindicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(
            appindicator.IndicatorStatus.ACTIVE)
        self._indicator.set_menu(menu)

        self._poll_source_id = GLib.timeout_add_seconds(
            self._INITIAL_DELAY,
            self._on_poll_timer,
        )

    # ------------------------------------------------------------------
    # Menu construction
    # ------------------------------------------------------------------

    def _build_menu(self) -> Gtk.Menu:
        """Build and return the right-click tray context menu."""
        menu = Gtk.Menu()

        show_item = Gtk.MenuItem(label="Show / Hide")
        show_item.connect("activate", lambda _: self._toggle_window())
        menu.append(show_item)

        refresh_item = Gtk.MenuItem(label="Check for Updates")
        refresh_item.connect("activate", lambda _: self._check_updates())
        menu.append(refresh_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _: self._quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _toggle_window(self) -> None:
        """Toggle window visibility.

        When opening the window while updates are pending,
        schedule a background refresh so the visible data matches the tray
        state.  The window is always shown immediately using cached data.
        """
        win = self._app.get_or_create_window()
        if win.get_visible() and self._shown:
            log.debug("toggle window hide")
            win.hide()
        else:
            log.debug("toggle window show: last count = %d", self._last_count)
            win.present()
            self._shown = True
            # Fixme: Do we want or need this. Maybe on first use only? or not at all?
            # if self._last_count > 0:
            #     GLib.idle_add(self._maybe_trigger_refresh, win)

    # pylint: disable=no-self-use; FIXME
    def _maybe_trigger_refresh(self, win: object) -> bool:
        """Idle callback: start a background refresh if one isn't already running."""
        if not getattr(win, "refresh_in_progress", False) and \
                not getattr(win, "install_in_progress", False):
            win.on_check_updates(None)  # type: ignore[union-attr]
        return False

    def _check_updates(self) -> None:
        """Show the window and trigger an update check."""
        log.debug("check updates")
        win = self._app.get_or_create_window(no_cache=True)
        win.present()
        self._shown = True
        GLib.idle_add(win.on_check_updates, None)

    def _quit(self) -> None:
        """Quit the application, releasing the hold() if in tray-only mode."""
        self._app.quit_from_tray()

    # ------------------------------------------------------------------
    # Background update-count polling
    # ------------------------------------------------------------------

    def _on_poll_timer(self) -> bool:
        """Periodic timer callback for background polling."""

        if not _read_pref("show_notifications"):
            log.debug("Background polling disabled")
            return True

        if self._poll_running:
            log.debug("Skipping poll: worker already running")
            return True

        log.debug("Starting background poll thread")

        self._poll_running = True

        threading.Thread(
            target=self._poll_worker_wrapper,
            daemon=True,
            name="bodhi-update-poller",
        ).start()

        return True

    def _poll_worker_wrapper(self):
        """Thread entry point for polling.

           Guarantees _poll_running is cleared on exit, even if an error occurs.
        """
        try:
            self._poll_worker()
        finally:
            log.debug("Background poll finished")
            self._poll_running = False

    def _poll_worker(self) -> None:
        """Read cached update state from backends (no refresh/privilege tool)."""
        log.debug("Background poll started")

        # Fixme: 1. this is a lot of code to wrap a try block around.
        #           Should be more specific on points of failure.
        #        2. should add log.debug msgs are excepts.

        try:
            initialize_registry()
        except Exception as exc:
            log.exception("Failed to initialize registry in background poll")
            GLib.idle_add(self.set_update_count, 0, "low")
            return

        count = 0
        severity = "low"
        registry = get_registry()

        for backend in registry.get_all_backends():
            backend_id = getattr(backend, "backend_id", getattr(backend, "__class__",
                                 str(backend)).__name__)
            try:
                log.debug("Polling backend: %s", backend_id)
                updates, _ = backend.get_updates()

                backend_count = 0
                for update in updates:
                    if getattr(update, "constraint", None) in (CONSTRAINT_HELD, CONSTRAINT_BLOCKED):
                        continue

                    count += 1
                    backend_count += 1

                    pkg_severity = get_pkg_severity(
                        getattr(update, "name", "") or "",
                        getattr(update, "category", "") or "",
                        getattr(update, "backend", "") or "",)

                    if pkg_severity == "high":
                        severity = "high"
                    elif pkg_severity == "medium" and severity != "high":
                        severity = "medium"

                log.debug("Backend %s → %d updates (total: %d, severity: %s)",
                          backend_id, backend_count, count, severity)

            except (OSError, RuntimeError, ValueError, AttributeError) as exc:
                log.debug("Backend %s skipped: %s", backend_id, exc)
                continue
            except Exception as exc:
                log.exception("Unexpected error in backend: %s", backend_id)
                continue

        log.debug("Poll completed: %d updates, severity=%s", count, severity)
        GLib.idle_add(self.set_update_count, count, severity)

    # ------------------------------------------------------------------
    # Indicator update
    # ------------------------------------------------------------------
    def _icon_name_for_state(self, count: int, severity: str) -> str:
        """Return the icon name that matches the current update state."""
        if count <= 0:
            return self._ICON_NAME
        return self._ICON_BY_SEVERITY.get(severity, self._ICON_BY_SEVERITY["low"])

    def set_update_count(self, count: int, severity: str = "medium") -> None:
        """Update indicator state from cached update count."""
        self._last_count = count
        if self._indicator is None:
            return

        if count <= 0:
            tooltip = "Update Manager"
        elif severity == "high":
            tooltip = "Update Manager - Security updates available"
        elif severity == "medium":
            tooltip = "Update Manager - Important updates available"
        else:
            tooltip = "Update Manager - Updates available"

        icon_name = self._icon_name_for_state(count, severity)
        self._indicator.set_icon_full(icon_name, tooltip)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        """Remove the tray icon and stop background polling."""
        if self._poll_source_id is not None:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None
        self._indicator.set_status(appindicator.IndicatorStatus.PASSIVE)
        self._indicator = None
