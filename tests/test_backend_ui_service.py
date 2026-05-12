"""Tests for BackendUIService."""

from __future__ import annotations

import pytest

from bodhi_update.backend_ui_service import BackendLoadResult, BackendUIService
from bodhi_update.backends import BackendMeta
from bodhi_update.models import (
    CONSTRAINT_BLOCKED,
    CONSTRAINT_HELD,
    CONSTRAINT_NORMAL,
    UpdateItem,
)


class FakeBackend:
    """Small backend test double."""

    def __init__(
        self,
        backend_id: str,
        display_name: str,
        *,
        available: bool = True,
        show_in_preferences: bool = False,
        filter_group: str | None = None,
        filter_label: str | None = None,
        filter_sort_order: int = 100,
        icon_name: str | None = None,
        updates: list[UpdateItem] | None = None,
        total_bytes: int = 0,
        busy: bool = False,
        busy_message: str = "",
        fail_updates: bool = False,
        install_command: list[str] | None = None,
    ) -> None:
        self.meta = BackendMeta(
            backend_id=backend_id,
            display_name=display_name,
            API="1",
            filter_group=filter_group,
            filter_label=filter_label,
            filter_sort_order=filter_sort_order,
            icon_name=icon_name,
            show_in_preferences=show_in_preferences,
        )
        self._available = available
        self._updates = updates or []
        self._total_bytes = total_bytes
        self._busy = busy
        self._busy_message = busy_message
        self._fail_updates = fail_updates
        self._install_command = install_command or ["install", backend_id]

    @property
    def backend_id(self) -> str:
        return self.meta.backend_id

    @property
    def display_name(self) -> str:
        return self.meta.display_name

    @property
    def filter_group(self) -> str | None:
        return self.meta.filter_group

    @property
    def filter_label(self) -> str | None:
        return self.meta.filter_label

    @property
    def filter_sort_order(self) -> int:
        return self.meta.filter_sort_order

    def is_available(self) -> bool:
        return self._available

    def get_updates(self) -> tuple[list[UpdateItem], int]:
        if self._fail_updates:
            raise RuntimeError("backend failed")
        return self._updates, self._total_bytes

    def check_busy(self) -> tuple[bool, str]:
        return self._busy, self._busy_message

    def build_install_command(
        self,
        packages: list[str] | None = None,
    ) -> list[str]:
        if packages is None:
            return [*self._install_command, "--all"]
        return [*self._install_command, *packages]


class FakeRegistry:
    """Small registry test double."""

    def __init__(self, backends: list[FakeBackend]) -> None:
        self._backends = {backend.backend_id: backend for backend in backends}

    def get_all_backends(self) -> list[FakeBackend]:
        return list(self._backends.values())

    def get_available_backends(self) -> list[FakeBackend]:
        return [
            backend
            for backend in self._backends.values()
            if backend.is_available()
        ]

    def get_backend(self, backend_id: str) -> FakeBackend | None:
        return self._backends.get(backend_id)


def make_update(
    name: str,
    *,
    backend: str = "apt",
    constraint: str = CONSTRAINT_NORMAL,
    size: int = 1024,
) -> UpdateItem:
    """Create a minimal UpdateItem for tests."""
    return UpdateItem(
        name=name,
        installed_version="1.0",
        candidate_version="2.0",
        size=size,
        origin="test",
        backend=backend,
        category="system",
        description="Test package",
        constraint=constraint,
    )


def patch_registry(
    monkeypatch: pytest.MonkeyPatch,
    registry: FakeRegistry,
) -> None:
    """Patch BackendUIService's registry accessor."""
    import bodhi_update.backend_ui_service as service_module

    monkeypatch.setattr(service_module, "get_registry", lambda: registry)


def test_is_backend_enabled_defaults_to_true() -> None:
    """Backends should be enabled by default when no preference exists."""
    service = BackendUIService({})

    assert service.is_backend_enabled("apt") is True


def test_is_backend_enabled_reads_visibility_preference() -> None:
    """Backend visibility preferences should disable matching backends."""
    service = BackendUIService(
        {
            "backend_visibility": {
                "apt": False,
                "flatpak": True,
            },
        }
    )

    assert service.is_backend_enabled("apt") is False
    assert service.is_backend_enabled("flatpak") is True
    assert service.is_backend_enabled("snap") is True


def test_is_backend_enabled_ignores_invalid_visibility_pref() -> None:
    """Invalid backend_visibility values should not disable backends."""
    service = BackendUIService({"backend_visibility": "not-a-dict"})

    assert service.is_backend_enabled("apt") is True


def test_get_all_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_all_backends should proxy the registry."""
    apt = FakeBackend("apt", "APT")
    snap = FakeBackend("snap", "Snap")
    patch_registry(monkeypatch, FakeRegistry([apt, snap]))

    service = BackendUIService({})

    assert service.get_all_backends() == [apt, snap]


def test_get_available_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_available_backends should return only available registry backends."""
    apt = FakeBackend("apt", "APT", available=True)
    snap = FakeBackend("snap", "Snap", available=False)
    patch_registry(monkeypatch, FakeRegistry([apt, snap]))

    service = BackendUIService({})

    assert service.get_available_backends() == [apt]


def test_get_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_backend should proxy registry lookup."""
    apt = FakeBackend("apt", "APT")
    patch_registry(monkeypatch, FakeRegistry([apt]))

    service = BackendUIService({})

    assert service.get_backend("apt") is apt
    assert service.get_backend("missing") is None


def test_get_preference_backends_filters_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only available preference-visible backends should be returned, sorted by name."""
    zed = FakeBackend(
        "zed",
        "Zed Backend",
        show_in_preferences=True,
    )
    alpha = FakeBackend(
        "alpha",
        "Alpha Backend",
        show_in_preferences=True,
    )
    hidden = FakeBackend(
        "hidden",
        "Hidden Backend",
        show_in_preferences=False,
    )
    unavailable = FakeBackend(
        "unavailable",
        "Unavailable Backend",
        available=False,
        show_in_preferences=True,
    )
    patch_registry(monkeypatch, FakeRegistry([zed, alpha, hidden, unavailable]))

    service = BackendUIService({})

    assert service.get_preference_backends() == [alpha, zed]


def test_get_visible_filter_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enabled available backends should expose their filter groups."""
    flatpak = FakeBackend(
        "flatpak",
        "Flatpak",
        filter_group="containers",
        filter_label="Containers",
        filter_sort_order=50,
    )
    snap = FakeBackend(
        "snap",
        "Snap",
        filter_group="containers",
        filter_label="Containers",
        filter_sort_order=50,
    )
    apt = FakeBackend("apt", "APT")
    patch_registry(monkeypatch, FakeRegistry([flatpak, snap, apt]))

    service = BackendUIService({})

    assert service.get_visible_filter_groups() == {
        "containers": ("Containers", 50),
    }


def test_get_visible_filter_groups_skips_disabled_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled backends should not contribute visible filter groups."""
    flatpak = FakeBackend(
        "flatpak",
        "Flatpak",
        filter_group="containers",
        filter_label="Containers",
    )
    patch_registry(monkeypatch, FakeRegistry([flatpak]))

    service = BackendUIService(
        {
            "backend_visibility": {
                "flatpak": False,
            },
        }
    )

    assert service.get_visible_filter_groups() == {}


def test_get_row_filter_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_row_filter_group should return the backend filter-group key."""
    flatpak = FakeBackend(
        "flatpak",
        "Flatpak",
        filter_group="containers",
        filter_label="Containers",
    )
    apt = FakeBackend("apt", "APT")
    patch_registry(monkeypatch, FakeRegistry([flatpak, apt]))

    service = BackendUIService({})

    assert service.get_row_filter_group("flatpak") == "containers"
    assert service.get_row_filter_group("apt") == ""
    assert service.get_row_filter_group("missing") == ""


def test_load_cached_updates_aggregates_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """load_cached_updates should aggregate updates and byte counts."""
    apt_update = make_update("bash", backend="apt", size=1024)
    flatpak_update = make_update("org.example.App", backend="flatpak", size=0)

    apt = FakeBackend(
        "apt",
        "APT",
        updates=[apt_update],
        total_bytes=1024,
    )
    flatpak = FakeBackend(
        "flatpak",
        "Flatpak",
        updates=[flatpak_update],
        total_bytes=0,
    )
    patch_registry(monkeypatch, FakeRegistry([apt, flatpak]))

    service = BackendUIService({})
    result = service.load_cached_updates()

    assert result == BackendLoadResult(
        updates=[apt_update, flatpak_update],
        total_bytes=1024,
        error_messages=[],
    )


def test_load_cached_updates_collects_backend_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend update failures should be collected without aborting the load."""
    apt_update = make_update("bash", backend="apt")

    apt = FakeBackend(
        "apt",
        "APT",
        updates=[apt_update],
        total_bytes=1024,
    )
    broken = FakeBackend(
        "broken",
        "Broken Backend",
        fail_updates=True,
    )
    patch_registry(monkeypatch, FakeRegistry([apt, broken]))

    service = BackendUIService({})
    result = service.load_cached_updates()

    assert result.updates == [apt_update]
    assert result.total_bytes == 1024
    assert result.error_messages == ["Broken Backend: backend failed"]


def test_count_actionable_updates() -> None:
    """Only normal updates should count as actionable."""
    updates = [
        make_update("normal", constraint=CONSTRAINT_NORMAL),
        make_update("held", constraint=CONSTRAINT_HELD),
        make_update("blocked", constraint=CONSTRAINT_BLOCKED),
    ]

    service = BackendUIService({})

    assert service.count_actionable_updates(updates) == 1


def test_check_any_backend_busy_returns_first_busy_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first busy backend message should be returned."""
    apt = FakeBackend("apt", "APT", busy=False)
    snap = FakeBackend(
        "snap",
        "Snap",
        busy=True,
        busy_message="Snap is busy.",
    )
    flatpak = FakeBackend(
        "flatpak",
        "Flatpak",
        busy=True,
        busy_message="Flatpak is busy.",
    )
    patch_registry(monkeypatch, FakeRegistry([apt, snap, flatpak]))

    service = BackendUIService({})

    assert service.check_any_backend_busy() == "Snap is busy."


def test_check_any_backend_busy_returns_none_when_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """None should be returned when no backend is busy."""
    apt = FakeBackend("apt", "APT", busy=False)
    patch_registry(monkeypatch, FakeRegistry([apt]))

    service = BackendUIService({})

    assert service.check_any_backend_busy() is None


def test_build_install_target_command_defaults_to_apt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No grouped packages should build the primary APT install command."""
    apt = FakeBackend("apt", "APT", install_command=["apt-install"])
    patch_registry(monkeypatch, FakeRegistry([apt]))

    service = BackendUIService({})

    assert service.build_install_target_command(None) == ["apt-install", "--all"]
    assert service.build_install_target_command({}) == ["apt-install", "--all"]


def test_build_install_target_command_errors_without_apt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No grouped packages should error if APT is unavailable."""
    patch_registry(monkeypatch, FakeRegistry([]))

    service = BackendUIService({})

    with pytest.raises(RuntimeError, match="Primary backend"):
        service.build_install_target_command(None)


def test_build_install_target_command_rejects_multi_backend_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installing multiple backend groups at once is not supported."""
    apt = FakeBackend("apt", "APT")
    snap = FakeBackend("snap", "Snap")
    patch_registry(monkeypatch, FakeRegistry([apt, snap]))

    service = BackendUIService({})

    with pytest.raises(RuntimeError, match="multiple package sources"):
        service.build_install_target_command(
            {
                "apt": ["bash"],
                "snap": ["firefox"],
            }
        )


def test_build_install_target_command_rejects_unknown_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown backend IDs should raise a clear RuntimeError."""
    patch_registry(monkeypatch, FakeRegistry([]))

    service = BackendUIService({})

    with pytest.raises(RuntimeError, match="unknown backend"):
        service.build_install_target_command({"missing": ["pkg"]})


def test_build_install_target_command_for_single_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single backend selection should delegate to that backend."""
    apt = FakeBackend("apt", "APT", install_command=["apt-install"])
    patch_registry(monkeypatch, FakeRegistry([apt]))

    service = BackendUIService({})

    assert service.build_install_target_command(
        {
            "apt": ["bash", "coreutils"],
        }
    ) == ["apt-install", "bash", "coreutils"]


@pytest.mark.parametrize(
    ("category", "backend_id", "constraint", "expected_icon"),
    [
        ("system", "apt", "held", "changes-prevent-symbolic"),
        ("system", "apt", "blocked_by_hold", "dialog-warning-symbolic"),
        ("security", "apt", CONSTRAINT_NORMAL, "security-high-symbolic"),
        ("kernel", "apt", CONSTRAINT_NORMAL, "applications-system-symbolic"),
    ],
)
def test_get_row_icon_priority_icons(
    monkeypatch: pytest.MonkeyPatch,
    category: str,
    backend_id: str,
    constraint: str,
    expected_icon: str,
) -> None:
    """Constraint and core category icons should have priority."""
    apt = FakeBackend(
        "apt",
        "APT",
        icon_name="custom-apt-icon",
    )
    patch_registry(monkeypatch, FakeRegistry([apt]))

    service = BackendUIService({})

    assert service.get_row_icon(category, backend_id, constraint) == expected_icon


def test_get_row_icon_uses_backend_icon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend metadata icon should be used after constraint/category checks."""
    flatpak = FakeBackend(
        "flatpak",
        "Flatpak",
        icon_name="flatpak-symbolic",
    )
    patch_registry(monkeypatch, FakeRegistry([flatpak]))

    service = BackendUIService({})

    assert (
        service.get_row_icon("system", "flatpak", CONSTRAINT_NORMAL)
        == "flatpak-symbolic"
    )


def test_get_row_icon_falls_back_to_generic_icon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows without a special icon should use the generic fallback."""
    apt = FakeBackend("apt", "APT")
    patch_registry(monkeypatch, FakeRegistry([apt]))

    service = BackendUIService({})

    assert (
        service.get_row_icon("system", "apt", CONSTRAINT_NORMAL)
        == "system-software-update-symbolic"
    )
