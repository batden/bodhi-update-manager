""" Dialogs used by the class UpdateManagerApplication. """

# flake8: noqa: E402
from __future__ import annotations

from dataclasses import dataclass
from gettext import bindtextdomain, textdomain
from gettext import gettext as _

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

APP_NAME = "bodhi-update-manager"
bindtextdomain(APP_NAME, "/usr/share/locale")
textdomain(APP_NAME)

from bodhi_update._version import __version__

ABOUT_TEXT = _(
    """Update Manager

A lightweight graphical update manager for Debian based distros."""
)

GPL_SHORT = _(
    """This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>."""
)


class AboutDialog(Gtk.Dialog):
    """About dialog for Bodhi Update Manager"""

    PAGES = {
        "update": ABOUT_TEXT,
        "website": _(
            """Website

https://github.com/flux-abyss/bodhi-update-manager"""
        ),
        "credits": _(
            """Credits

Developers:
    Joseph “flux.abyss” Wiley
    Robert “ylee” Wiley
    Diego “diekrz2” K.

Translation:
    Hugo Carvalho
    Alejandro Díaz
    Diego “diekrz2” K.
    Indraneel Rajeevan
    Štefan Uram"""
        ),
        "license": _(
            """Copyright © 2026 Joseph “flux.abyss” Wiley

"""
        ) + GPL_SHORT,
    }

    BUTTONS = [
        ("update", _("Update Manager")),
        ("website", _("Website")),
        ("credits", _("Credits")),
        ("license", _("License")),
    ]

    def __init__(self, parent) -> None:
        super().__init__(
            title=_("About"),
            transient_for=parent,
            modal=True,
            destroy_with_parent=True
        )
        self.set_border_width(10)
        self.set_default_size(600, 400)
        self.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)

        self._build_ui()
        self._set_text(self.PAGES["update"])

    def _build_ui(self) -> None:
        content = self.get_content_area()

        outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content.pack_start(outer_box, True, True, 0)

        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left_box.set_size_request(160, -1)
        outer_box.pack_start(left_box, False, False, 0)

        icon = Gtk.Image.new_from_icon_name("bodhi-update-manager",
                                            Gtk.IconSize.DIALOG)
        icon.set_pixel_size(200)
        left_box.pack_start(icon, False, False, 0)

        version_label = Gtk.Label()
        version_label.set_markup(f"<b>{_('Version:')}</b> {__version__}")
        version_label.set_justify(Gtk.Justification.CENTER)
        left_box.pack_start(version_label, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_size_request(-1, 10)
        left_box.pack_start(spacer, False, False, 0)

        for key, label in self.BUTTONS:
            btn = Gtk.Button(label=label)
            btn.set_hexpand(False)
            btn.connect("clicked", self._on_about_button_clicked, key)
            left_box.pack_start(btn, False, False, 0)

        left_box.pack_start(Gtk.Box(), True, True, 0)

        right_frame = Gtk.Frame()
        outer_box.pack_start(right_frame, True, True, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        right_frame.add(scrolled)

        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_monospace(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.textview.set_left_margin(10)
        self.textview.set_right_margin(10)
        self.textview.set_top_margin(10)
        self.textview.set_bottom_margin(10)
        scrolled.add(self.textview)

    def _set_text(self, text: str) -> None:
        buffer_ = self.textview.get_buffer()
        buffer_.set_text(text)

    def _on_about_button_clicked(self, _button, key: str) -> None:
        self._set_text(self.PAGES[key])


@dataclass
class PreferencesLabels:
    """All translatable label strings for PreferencesDialog."""

    title: str
    notifications_label: str
    held_label: str
    welcome_label: str
    cancel_label: str
    apply_label: str


@dataclass
class PreferencesState:
    """Current pref values used to initialise PreferencesDialog widgets."""

    show_notifications: bool
    show_held_packages: bool
    show_welcome: bool
    backend_states: list[tuple[str, str, bool]]


class PreferencesDialog(Gtk.Dialog):
    """Preferences dialog for Bodhi Update Manager."""

    def __init__(
        self,
        parent: Gtk.Window,
        labels: PreferencesLabels,
        state: PreferencesState,
    ) -> None:
        """
        state.backend_states: list of (backend_id, display_label, is_enabled) tuples.
        """
        super().__init__(
            title=labels.title,
            transient_for=parent,
            modal=True,
        )

        self.add_button(labels.cancel_label, Gtk.ResponseType.CANCEL)
        self.add_button(labels.apply_label, Gtk.ResponseType.APPLY)

        self._backend_checks: dict[str, Gtk.CheckButton] = {}

        content = self.get_content_area()
        content.set_spacing(8)
        content.set_border_width(8)

        # --- General options ---

        self.notif_check = Gtk.CheckButton(label=labels.notifications_label)
        self.notif_check.set_active(state.show_notifications)
        content.pack_start(self.notif_check, False, False, 0)

        self.held_check = Gtk.CheckButton(label=labels.held_label)
        self.held_check.set_active(state.show_held_packages)
        content.pack_start(self.held_check, False, False, 0)

        self.welcome_check = Gtk.CheckButton(label=labels.welcome_label)
        self.welcome_check.set_active(state.show_welcome)
        content.pack_start(self.welcome_check, False, False, 0)

        # --- Backend section (only if any backends exist) ---

        if state.backend_states:
            sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            content.pack_start(sep, False, False, 6)

            backend_label = Gtk.Label(label=_("Backends"))
            backend_label.set_xalign(0)
            backend_label.get_style_context().add_class("heading")
            content.pack_start(backend_label, False, False, 0)

            for backend_id, label, enabled in state.backend_states:
                check = Gtk.CheckButton(label=label)
                check.set_active(enabled)
                content.pack_start(check, False, False, 0)
                self._backend_checks[backend_id] = check

        self.show_all()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_values(self) -> dict:
        """Return dialog values as a plain dict."""
        return {
            "show_notifications": self.notif_check.get_active(),
            "show_held_packages": self.held_check.get_active(),
            "show_welcome": self.welcome_check.get_active(),
            "backend_visibility": {
                backend_id: check.get_active()
                for backend_id, check in self._backend_checks.items()
            },
        }


class WelcomeDialog(Gtk.Dialog):
    """First-run welcome dialog for the Update Manager."""

    def __init__(self, parent: Gtk.Window, show_on_startup: bool = True) -> None:
        super().__init__(
            title=_("Welcome"),
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )

        self.set_border_width(10)
        self.set_default_size(560, 520)
        # Fix me
        # self.add_button(_("Help"), Gtk.ResponseType.HELP)
        self.add_button(_("OK"), Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        self.show_startup_check = Gtk.CheckButton(
            label=_("Show this welcome screen on startup")
        )
        self.show_startup_check.set_active(show_on_startup)

        self._build_ui()
        self.show_all()

    def _build_ui(self) -> None:
        content = self.get_content_area()
        content.set_spacing(12)

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer_box.set_border_width(6)
        outer_box.set_hexpand(True)
        outer_box.set_vexpand(True)
        content.pack_start(outer_box, True, True, 0)

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header_box.set_border_width(12)
        outer_box.pack_start(header_box, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_hexpand(True)
        scrolled.set_vexpand(True)

        outer_box.pack_start(scrolled, True, True, 0)
        body_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body_box.set_border_width(6)
        scrolled.add(body_box)

        title = Gtk.Label()
        title.set_markup("<b>%s</b>" % _("Welcome to the Update Manager"))
        title.set_xalign(0.0)
        header_box.pack_start(title, False, False, 0)

        intro = Gtk.Label(
            label=_(
                "This update manager helps you review, select, and install available "
                "updates from supported package sources."
            )
        )
        intro.set_line_wrap(True)
        intro.set_xalign(0.0)
        header_box.pack_start(intro, False, False, 0)

        self._add_info_row(
            body_box,
            "security-high-symbolic",
            _("Security and system updates"),
            _(
                "Important updates are highlighted so security fixes, kernel updates, "
                "and core system packages are easier to notice."
            ),
        )

        self._add_info_row(
            body_box,
            "view-list-symbolic",
            _("Review before installing"),
            _(
                "Updates are shown in a clear list with package names, versions, "
                "download sizes, sources, and optional descriptions."
            ),
        )

        self._add_info_row(
            body_box,
            "package-x-generic",
            _("Multiple package sources"),
            _(
                "The update list can include supported backends such as Debian/Ubuntu "
                "packages, Snap packages, and Flatpak packages when they are available."
            ),
        )

        footer = Gtk.Label(
            label=_(
                "The goal is to provide a flexible update tool that stays "
                "out of your way while still giving you clear control over what gets "
                "updated."
            )
        )
        footer.set_line_wrap(True)
        footer.set_xalign(0.0)
        body_box.pack_start(footer, False, False, 0)
        outer_box.pack_start(self.show_startup_check, False, False, 0)

    def _add_info_row(
        self,
        parent: Gtk.Box,
        icon_name: str,
        heading: str,
        text: str,
    ) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_border_width(6)
        parent.pack_start(row, False, True, 0)

        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        icon.set_valign(Gtk.Align.START)
        row.pack_start(icon, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row.pack_start(text_box, True, True, 0)

        heading_label = Gtk.Label()
        heading_label.set_markup(f"<b>{heading}</b>")
        heading_label.set_xalign(0.0)
        text_box.pack_start(heading_label, False, False, 0)

        body_label = Gtk.Label(label=text)
        body_label.set_line_wrap(True)
        body_label.set_xalign(0.0)
        text_box.pack_start(body_label, False, False, 0)

    def get_show_on_startup(self) -> bool:
        """Return whether the welcome dialog should appear on startup."""
        return self.show_startup_check.get_active()


class Message(Gtk.MessageDialog):
    """Simple message dialog that destroys itself after running."""
    def __init__(
        self,
        title: str,
        text: str,
        text2: str | None = None,
        parent: Gtk.Window | None = None,
    ) -> None:
        super().__init__(
            transient_for=parent,
            flags=Gtk.DialogFlags.MODAL if parent is not None else 0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.NONE,
        )

        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_title(title)
        self.set_markup(text)
        self.add_button(_("OK"), Gtk.ResponseType.OK)

        if text2:
            self.format_secondary_markup(text2)

    def show(self) -> int:
        """Run the dialog, destroy it, and return the response."""
        try:
            return self.run()
        finally:
            self.destroy()
