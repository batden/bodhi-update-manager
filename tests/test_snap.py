"""Tests for the Snap update backend."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from bodhi_update.models import CONSTRAINT_HELD, CONSTRAINT_NORMAL
from bodhi_update.plugins.snap import SnapBackend


def completed(
    stdout: str = "",
    stderr: bytes | str = b"",
    returncode: int = 0,
):
    """Build a lightweight subprocess.CompletedProcess-like object."""
    return SimpleNamespace(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
    )


def test_snap_metadata() -> None:
    backend = SnapBackend()

    assert backend.backend_id == "snap"
    assert backend.display_name == "Snap Packages"
    assert backend.filter_group == "snap"
    assert backend.filter_label == "Snap"
    assert backend.filter_sort_order == 200
    assert backend.meta.show_in_preferences is True
    assert backend.meta.icon_name == "package-x-generic-symbolic"


def test_is_available_false_when_snap_missing(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.shutil.which",
                        lambda _name: None)

    assert SnapBackend().is_available() is False


def test_is_available_true_when_snap_list_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.shutil.which",
                        lambda _name: "/usr/bin/snap")

    def fake_run(argv, **kwargs):
        assert argv == ["snap", "list"]
        assert kwargs["timeout"] == 8
        assert kwargs["check"] is False
        return completed(returncode=0, stderr=b"")

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)

    assert SnapBackend().is_available() is True


def test_is_available_false_when_snap_list_fails(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.shutil.which",
                        lambda _name: "/usr/bin/snap")
    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(returncode=1, stderr=b"error"),
    )

    assert SnapBackend().is_available() is False


def test_is_available_false_when_snapd_cannot_connect(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.shutil.which",
                        lambda _name: "/usr/bin/snap")
    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(
            returncode=0,
            stderr=b"error: cannot connect to snapd socket",
        ),
    )

    assert SnapBackend().is_available() is False


def test_is_available_false_on_timeout(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.shutil.which",
                        lambda _name: "/usr/bin/snap")

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["snap", "list"], timeout=8)

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)

    assert SnapBackend().is_available() is False


def test_is_available_false_on_os_error(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.shutil.which",
                        lambda _name: "/usr/bin/snap")

    def fake_run(*_args, **_kwargs):
        raise OSError("snap failed")

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)

    assert SnapBackend().is_available() is False


def test_check_busy_returns_not_busy() -> None:
    assert SnapBackend().check_busy() == (False, "")


def test_refresh_is_noop_success() -> None:
    assert SnapBackend().refresh() == (True, "")


def test_supports_hold_true() -> None:
    assert SnapBackend().supports_hold() is True


def test_build_hold_command_hold(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.require_pkexec",
                        lambda: "pkexec")

    assert SnapBackend().build_hold_command("firefox", True) == [
        "pkexec",
        "/usr/libexec/um-actions-snap",
        "hold",
        "firefox",
    ]


def test_build_hold_command_unhold(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.require_pkexec",
                        lambda: "pkexec")

    assert SnapBackend().build_hold_command("firefox", False) == [
        "pkexec",
        "/usr/libexec/um-actions-snap",
        "unhold",
        "firefox",
    ]


def test_parse_snap_table_skips_header_and_blank_lines() -> None:
    stdout = """
Name      Version      Rev    Tracking       Publisher      Notes

firefox   126.0        4259   latest/stable  mozilla**      -
core22    20240408     1380   latest/stable  canonical**    base
"""

    rows = SnapBackend._parse_snap_table(stdout)

    assert rows == [
        ["firefox", "126.0", "4259", "latest/stable", "mozilla**", "-"],
        ["core22", "20240408", "1380", "latest/stable", "canonical**", "base"],
    ]


def test_refresh_time_stamp_returns_last_value(monkeypatch) -> None:
    stdout = """timer: 00:00~24:00/4
last: today at 10:00 EDT
next: today at 16:00 EDT
"""

    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(stdout=stdout, returncode=0),
    )

    assert SnapBackend._refresh_time_stamp() == "today at 10:00 EDT"


def test_refresh_time_stamp_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(stdout="timer: 00:00~24:00/4",
                                            returncode=0),
    )

    assert SnapBackend._refresh_time_stamp() is None


def test_refresh_time_stamp_returns_none_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(stdout="", returncode=1),
    )

    assert SnapBackend._refresh_time_stamp() is None


def test_refresh_time_stamp_returns_none_on_timeout(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["snap", "refresh", "--time"],
            timeout=8,
        )

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)

    assert SnapBackend._refresh_time_stamp() is None


def test_installed_info_returns_version_and_held_state(monkeypatch) -> None:
    stdout = """Name      Version      Rev    Tracking       Publisher      Notes
firefox   125.0        4250   latest/stable  mozilla**      held
core22    20240408     1380   latest/stable  canonical**    base
code      1.90.0       100    latest/stable  vscode**       classic,held
"""

    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(stdout=stdout, returncode=0),
    )

    assert SnapBackend()._installed_info() == {
        "firefox": ("125.0", True),
        "core22": ("20240408", False),
        "code": ("1.90.0", True),
    }


def test_installed_info_returns_empty_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(stdout="", returncode=1),
    )

    assert SnapBackend()._installed_info() == {}


def test_installed_info_returns_empty_on_timeout(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["snap", "list"], timeout=10)

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)

    assert SnapBackend()._installed_info() == {}


def test_query_pending_refreshes_returns_stdout(monkeypatch) -> None:
    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(stdout="pending snaps",
                                            returncode=0),
    )

    assert SnapBackend()._query_pending_refreshes() == "pending snaps"


def test_query_pending_refreshes_returns_empty_on_timeout(monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["snap", "refresh", "--list"],
            timeout=20,
        )

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)

    assert SnapBackend()._query_pending_refreshes() == ""


def test_get_updates_returns_snap_update_items(monkeypatch) -> None:
    refresh_output = """Name      Version      Rev    Size    Publisher      Notes
firefox   126.0        4260   250MB   mozilla**      -
core22    20240501     1400   75MB    canonical**    base
"""

    installed_output = """Name      Version      Rev    Tracking       Publisher      Notes
firefox   125.0        4250   latest/stable  mozilla**      held
core22    20240408     1380   latest/stable  canonical**    base
"""

    def fake_run(argv, **_kwargs):
        if argv == ["snap", "refresh", "--list"]:
            return completed(stdout=refresh_output, returncode=0)
        if argv == ["snap", "list"]:
            return completed(stdout=installed_output, returncode=0)
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)
    monkeypatch.setattr("bodhi_update.plugins.snap.is_user_security_package",
                        lambda name: name == "firefox")

    updates, total_bytes = SnapBackend().get_updates()

    assert total_bytes == 0
    assert [item.name for item in updates] == ["firefox", "core22"]

    firefox = updates[0]
    assert firefox.installed_version == "125.0"
    assert firefox.candidate_version == "126.0"
    assert firefox.size == 0
    assert firefox.origin == "snap"
    assert firefox.backend == "snap"
    assert firefox.category == "security"
    assert firefox.description == "Held Snap package"
    assert firefox.constraint == CONSTRAINT_HELD

    core22 = updates[1]
    assert core22.installed_version == "20240408"
    assert core22.candidate_version == "20240501"
    assert core22.category == "snap"
    assert core22.description == "Snap package"
    assert core22.constraint == CONSTRAINT_NORMAL


def test_get_updates_uses_dash_for_unknown_installed_version(monkeypatch) -> None:
    refresh_output = """Name      Version      Rev    Size    Publisher      Notes
firefox   126.0        4260   250MB   mozilla**      -
"""

    def fake_run(argv, **_kwargs):
        if argv == ["snap", "refresh", "--list"]:
            return completed(stdout=refresh_output, returncode=0)
        if argv == ["snap", "list"]:
            return completed(stdout="", returncode=1)
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)
    monkeypatch.setattr("bodhi_update.plugins.snap.is_user_security_package",
                        lambda _name: False)

    updates, total_bytes = SnapBackend().get_updates()

    assert total_bytes == 0
    assert len(updates) == 1
    assert updates[0].name == "firefox"
    assert updates[0].installed_version == "-"
    assert updates[0].constraint == CONSTRAINT_NORMAL


def test_get_updates_returns_empty_when_refresh_output_empty(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return completed(stdout="", returncode=1)

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)

    updates, total_bytes = SnapBackend().get_updates()

    assert updates == []
    assert total_bytes == 0
    assert calls == [["snap", "refresh", "--list"]]


def test_get_update_summary_counts_pending_refreshes(monkeypatch) -> None:
    backend = SnapBackend()
    refresh_output = """Name      Version      Rev    Size    Publisher      Notes
firefox   126.0        4260   250MB   mozilla**      -
core22    20240501     1400   75MB    canonical**    base
"""

    monkeypatch.setattr(backend, "_refresh_time_stamp", lambda: "stamp-1")
    monkeypatch.setattr(backend, "_query_pending_refreshes",
                        lambda: refresh_output)

    summary = backend.get_update_summary()

    assert summary.count == 2
    assert summary.severity == "low"


def test_get_update_summary_reuses_cache_when_stamp_unchanged(monkeypatch) -> None:
    backend = SnapBackend()

    monkeypatch.setattr(backend, "_refresh_time_stamp", lambda: "stamp-1")
    monkeypatch.setattr(
        backend,
        "_query_pending_refreshes",
        lambda: "Name Version Rev Size Publisher Notes\nfirefox 126 1 1MB pub -",
    )

    first = backend.get_update_summary()

    def fail_query():
        raise AssertionError("should not query pending refreshes again")

    monkeypatch.setattr(backend, "_query_pending_refreshes", fail_query)

    second = backend.get_update_summary()

    assert second == first
    assert second.count == 1


def test_get_update_summary_uses_fallback_ttl_when_stamp_unavailable(
    monkeypatch,
) -> None:
    backend = SnapBackend()
    backend._last_summary_check = 100.0

    monkeypatch.setattr("bodhi_update.plugins.snap.time.monotonic",
                        lambda: 120.0)
    monkeypatch.setattr(backend, "_refresh_time_stamp", lambda: None)

    def fail_query():
        raise AssertionError("should not query during fallback TTL window")

    monkeypatch.setattr(backend, "_query_pending_refreshes", fail_query)

    summary = backend.get_update_summary()

    assert summary.count == 0
    assert summary.severity == "low"


def test_build_install_command_for_explicit_packages(monkeypatch) -> None:
    monkeypatch.setattr("bodhi_update.plugins.snap.require_pkexec",
                        lambda: "pkexec")

    argv = SnapBackend().build_install_command(["firefox", "core22"])

    assert argv == [
        "pkexec",
        "/usr/libexec/um-actions-snap",
        "refresh",
        "firefox",
        "core22",
    ]


def test_build_install_command_discovers_packages_when_none(monkeypatch) -> None:
    refresh_output = """Name      Version      Rev    Size    Publisher      Notes
firefox   126.0        4260   250MB   mozilla**      -
core22    20240501     1400   75MB    canonical**    base
"""

    installed_output = """Name      Version      Rev    Tracking       Publisher      Notes
firefox   125.0        4250   latest/stable  mozilla**      -
core22    20240408     1380   latest/stable  canonical**    base
"""

    def fake_run(argv, **_kwargs):
        if argv == ["snap", "refresh", "--list"]:
            return completed(stdout=refresh_output, returncode=0)
        if argv == ["snap", "list"]:
            return completed(stdout=installed_output, returncode=0)
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr("bodhi_update.plugins.snap.subprocess.run", fake_run)
    monkeypatch.setattr("bodhi_update.plugins.snap.require_pkexec",
                        lambda: "pkexec")
    monkeypatch.setattr("bodhi_update.plugins.snap.is_user_security_package",
                        lambda _name: False)

    argv = SnapBackend().build_install_command()

    assert argv == [
        "pkexec",
        "/usr/libexec/um-actions-snap",
        "refresh",
        "firefox",
        "core22",
    ]


def test_build_install_command_returns_true_when_no_packages(monkeypatch) -> None:
    monkeypatch.setattr(
        "bodhi_update.plugins.snap.subprocess.run",
        lambda *_args, **_kwargs: completed(stdout="", returncode=1),
    )

    argv = SnapBackend().build_install_command()

    assert argv == ["true"]
