"""Install/progress controller for Bodhi Update Manager."""

from __future__ import annotations

import logging
import os
from gettext import bindtextdomain, textdomain
from gettext import gettext as _

import gi

gi.require_version("Vte", "2.91")
from gi.repository import GLib, Vte

from bodhi_update.dialogs import Message

APP_NAME = "bodhi-update-manager"
log = logging.getLogger(APP_NAME)

bindtextdomain(APP_NAME, "/usr/share/locale")
textdomain(APP_NAME)


class InstallController:
    """Handle install/auth flow and VTE-driven progress UI.

    This controller intentionally does not know about APT, Snap, Flatpak,
    helper paths, or package-manager actions. Backends build argv; this class
    only presents progress and runs argv in the VTE.
    """

    def __init__(self, window) -> None:
        self.window = window
        self.install_state: str = "IDLE"
        self.install_output_started = False
        self.install_pulse_source_id: int | None = None

    def _pulse_install_progress(self) -> bool:
        if not self.window.install_in_progress or not self.install_output_started:
            self.install_pulse_source_id = None
            return False

        self.window.install_progress.pulse()
        return True

    def start_install_progress(self, title: str) -> None:
        """Prepare the install UI and enter AUTH_PENDING state."""
        self.install_state = "AUTH_PENDING"
        self.window.set_install_busy(True)
        self.install_output_started = False

        self.window.stack.set_visible_child_name("install")
        self.window.install_title_label.set_markup(
            f"<b>{GLib.markup_escape_text(title)}</b>")
        self.window.install_phase_label.set_text(_("Waiting for authentication..."))
        self.window.install_progress.set_fraction(0.0)
        self.window.install_progress.set_show_text(True)
        self.window.install_progress.set_text(_("Waiting for authentication..."))
        self.window.set_status(_("Waiting for authorization..."))

        self.window.install_details_revealer.set_reveal_child(False)
        self.window.show_details_button.set_active(False)
        self.window.show_details_button.set_label(_("Show Details"))

        if self.install_pulse_source_id is not None:
            GLib.source_remove(self.install_pulse_source_id)
            self.install_pulse_source_id = None

        try:
            self.window.install_terminal.reset(True, True)
        except (AttributeError, TypeError, RuntimeError):
            pass

    def mark_install_running(self) -> bool:
        """Transition install UI from AUTH_PENDING to RUNNING."""
        if self.install_state != "AUTH_PENDING":
            return False

        self.install_state = "RUNNING"
        self.install_output_started = True
        self.window.install_phase_label.set_text(_("This may take a few minutes."))
        self.window.install_progress.set_text(_("Installing updates..."))
        self.window.set_status(_("Installing updates..."))

        self.window.install_details_revealer.set_reveal_child(True)
        self.window.show_details_button.set_active(True)
        self.window.show_details_button.set_label(_("Hide Details"))
        self.window.install_terminal.grab_focus()

        if self.install_pulse_source_id is None:
            self.install_pulse_source_id = GLib.timeout_add(
                150,
                self._pulse_install_progress,
            )

        return False

    def on_spawn_complete(self, _terminal, pid, error, _user_data=None) -> None:
        """VTE spawn_async callback for hard spawn failures."""
        if error is not None:
            log.error("Spawn failed: %s", error.message)
            self.install_state = "FAILED"
            self.window.set_install_busy(False)
            self.window.install_progress.set_fraction(0.0)
            self.window.install_progress.set_text(_("Failed"))
            self.window.install_phase_label.set_text(
                _("Failed to start installation. See Details below.")
            )
            self.window.install_details_revealer.set_reveal_child(True)
            self.window.show_details_button.set_active(True)
            self.window.show_details_button.set_label(_("Hide Details"))
            self.window.set_status(_("Failed to start installation."))
            return

        log.info("Install process spawned (pid %s).", pid)

    def spawn_install_command(self, argv: list[str]) -> None:
        """Spawn argv directly in the VTE terminal."""
        envv = [f"{key}={value}" for key, value in os.environ.items()]

        self.window.install_terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            os.getcwd(),
            argv,
            envv,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            self.on_spawn_complete,
            None,
        )

    def launch_install(self, argv: list[str], title: str) -> None:
        """Launch an install command.

        The argv must already be built by the selected backend.
        """
        log.info("Starting installation: %s", title)
        log.debug("Command: %s", argv)

        self.start_install_progress(title)
        self.spawn_install_command(argv)
        GLib.idle_add(self.mark_install_running)

    def finish_install_success(self) -> None:
        """Update the UI for a successful install."""
        log.info("Installation completed successfully.")
        self.install_state = "COMPLETE"
        self.window.set_install_busy(False)
        self.window.install_progress.set_fraction(1.0)
        self.window.install_progress.set_text(_("Complete"))
        self.window.install_phase_label.set_text(
            _("Updates installed successfully.")
        )
        self.window.set_status(_("Ready"))

    def finish_install_failure(self, exit_code: int) -> None:
        """Update the UI for a failed install."""
        log.error("Installation failed with exit code: %s", exit_code)
        self.install_state = "FAILED"
        self.window.set_install_busy(False)
        self.window.install_progress.set_fraction(0.0)
        self.window.install_progress.set_text(_("Failed"))
        self.window.install_phase_label.set_text(
            _("Update failed. Exit code: %(exit_code)s. See Details below.")
            % {"exit_code": exit_code}
        )
        self.window.install_details_revealer.set_reveal_child(True)
        self.window.show_details_button.set_active(True)
        self.window.show_details_button.set_label(_("Hide Details"))
        self.window.set_status(
            _("Update failed. Exit code: %(exit_code)s")
            % {"exit_code": exit_code}
        )

        details = self.window._terminal_text().strip()
        if details:
            message = details.splitlines()[-1]
        else:
            message = _("The install command exited with code %(exit_code)s.") % {
                "exit_code": exit_code
            }

        GLib.idle_add(self.show_install_error, message)

    def show_install_error(self, message: str) -> bool:
        """Show an install failure message dialog on the GTK thread."""
        Message(
            _("Installation failed"),
            _("Could not install selected updates."),
            message,
            parent=self.window,
        ).show()
        return False
