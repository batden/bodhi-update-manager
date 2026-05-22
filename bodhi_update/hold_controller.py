"""Backend package-action controller for Bodhi Update Manager."""

from __future__ import annotations

import logging
import subprocess
import threading
from gettext import bindtextdomain, textdomain
from gettext import gettext as _

from gi.repository import GLib

from bodhi_update.backends import get_registry
from bodhi_update.models import CONSTRAINT_NORMAL
from bodhi_update.utils import format_size

APP_NAME = "bodhi-update-manager"
log = logging.getLogger(APP_NAME)

bindtextdomain(APP_NAME, "/usr/share/locale")
textdomain(APP_NAME)


class PackageActionController:
    """Handle backend package actions such as hold/unhold.

    The controller owns the UI flow.  Individual backends own the package
    manager semantics and return the argv needed to perform the action.
    """

    def __init__(self, window) -> None:
        self.window = window

    def _get_backend(self, backend_id: str):
        """Return a registered backend by id, or None."""
        return get_registry().get_backend(backend_id)

    def backend_supports_hold(self, backend_id: str) -> bool:
        """Return True if *backend_id* supports hold/unhold actions."""
        backend = self._get_backend(backend_id)
        log.debug("HERE")
        if backend is None:
            return False
        return bool(backend.supports_hold())

    def reload_backend_rows(self, backend_id: str) -> None:
        """Re-query one backend, leaving other backend rows intact."""
        from bodhi_update.app import Col

        backend = self._get_backend(backend_id)
        if backend is None:
            return

        other_rows = [
            list(row)
            for row in self.window.store
            if row[Col.BACKEND] != backend_id
        ]

        backend_updates = []
        backend_bytes = 0

        try:
            backend_updates, backend_bytes = backend.get_updates()
        except (OSError, RuntimeError, ValueError) as exc:
            log.error(
                "Backend %s get_updates failed after package action: %s",
                backend.display_name,
                exc,
            )
            GLib.idle_add(
                self.window.set_status,
                _("%(name)s reload failed. (%(exc)s)") % {
                    "name": backend.display_name,
                    "exc": exc,
                },
            )
            return

        show_desc = self.window.prefs.get("show_descriptions", True)

        self.window.store.freeze_notify()
        try:
            self.window.store.clear()

            for row in other_rows:
                self.window.store.append(row)

            for update in backend_updates:
                constraint = update.constraint
                icon = self.window.backend_service.get_row_icon(
                    update.category,
                    update.backend,
                    constraint,
                )
                pkg_markup = self.window.build_pkg_markup(
                    update.name,
                    update.description,
                    show_desc,
                    constraint,
                )
                size_str = (
                    _("N/A")
                    if update.size == 0 and update.backend != "apt"
                    else format_size(update.size)
                )
                filter_group = self.window.backend_service.get_row_filter_group(
                    update.backend,
                )

                self.window.store.append([
                    False,
                    pkg_markup,
                    update.installed_version,
                    update.candidate_version,
                    size_str,
                    update.origin,
                    update.name,
                    update.category,
                    filter_group,
                    update.backend,
                    icon,
                    update.size,
                    update.description or _("System package"),
                    constraint,
                ])
        finally:
            self.window.store.thaw_notify()

        other_bytes = sum(
            row[Col.RAW_SIZE]
            for row in self.window.store
            if row[Col.BACKEND] != backend_id
        )
        actionable = sum(
            1
            for row in self.window.store
            if row[Col.HELD] == CONSTRAINT_NORMAL
        )

        self.window.update_count_status(
            actionable,
            backend_bytes + other_bytes,
            cached=True,
        )

    def do_hold_toggle(
        self,
        backend_id: str,
        package_name: str,
        hold: bool,
    ) -> None:
        """Run a backend hold/unhold action."""
        if self.window.refresh_in_progress or self.window.install_in_progress:
            return

        backend = self._get_backend(backend_id)
        if backend is None:
            self.window.set_status(
                _("Unknown backend: %(backend)s") % {"backend": backend_id}
            )
            return

        if not backend.supports_hold():
            self.window.set_status(
                _("%(name)s does not support hold/unhold actions.")
                % {"name": backend.display_name}
            )
            return

        running_msg = (
            _("Locking package...")
            if hold
            else _("Unlocking package...")
        )
        self.window.set_status(_("Waiting for authorization..."))

        def _worker() -> None:
            try:
                argv = backend.build_hold_command(package_name, hold)
            except (NotImplementedError, RuntimeError, ValueError) as exc:
                GLib.idle_add(self.window.set_status, str(exc))
                return
            GLib.idle_add(self.window.set_status, running_msg)
            try:
                result = subprocess.run(
                    argv,
                    capture_output=True,
                    check=False,
                )
            except OSError as exc:
                GLib.idle_add(
                    self.window.set_status,
                    _("Failed to launch package action: %(exc)s")
                    % {"exc": exc},
                )
                return

            if result.returncode != 0:
                err_lines = (
                    (result.stderr or b"")
                    .decode(errors="replace")
                    .strip()
                    .splitlines()
                )
                msg = err_lines[0] if err_lines else _(
                    "Package action failed (unknown error)"
                )
                GLib.idle_add(self.window.set_status, msg)
                return

            if hold:
                status = _(
                    "%(backend)s package '%(name)s' is now held."
                ) % {
                    "backend": backend.display_name,
                    "name": package_name,
                }
            else:
                status = _(
                    "%(backend)s package '%(name)s' is no longer held."
                ) % {
                    "backend": backend.display_name,
                    "name": package_name,
                }

            GLib.idle_add(self.reload_backend_rows, backend_id)
            GLib.idle_add(self.window.set_status, status)
            GLib.timeout_add_seconds(
                3,
                self.window.restore_current_update_status,
            )

        threading.Thread(target=_worker, daemon=True).start()
