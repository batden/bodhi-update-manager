"""Tests for user-defined security package policy."""

from __future__ import annotations

from pathlib import Path

from bodhi_update import security_policy


def _write_policy(config_home: Path, text: str) -> Path:
    policy_dir = config_home / "bodhi-update-manager"
    policy_dir.mkdir(parents=True)
    policy_path = policy_dir / "security-packages.conf"
    policy_path.write_text(text, encoding="utf-8")
    return policy_path


def test_missing_policy_file_uses_defaults(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    patterns = security_policy.reload_security_patterns()

    assert "firefox" in patterns
    assert "chromium*" in patterns
    assert security_policy.is_user_security_package("firefox")
    assert security_policy.is_user_security_package("chromium-browser")
    assert not security_policy.is_user_security_package("nano")


def test_policy_file_adds_user_patterns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _write_policy(
        tmp_path,
        """
        # User security policy
        my-browser
        custom-webkit*
        """,
    )

    patterns = security_policy.reload_security_patterns()

    assert "my-browser" in patterns
    assert "custom-webkit*" in patterns
    assert security_policy.is_user_security_package("my-browser")
    assert security_policy.is_user_security_package("custom-webkit2gtk")
    assert not security_policy.is_user_security_package("random-package")


def test_policy_file_ignores_blank_lines_and_comments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _write_policy(
        tmp_path,
        """

        # comment
        brave-browser

        # another comment
        """,
    )

    patterns = security_policy.reload_security_patterns()

    assert "brave-browser" in patterns
    assert "#" not in patterns
    assert "" not in patterns


def test_duplicate_patterns_are_removed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _write_policy(
        tmp_path,
        """
        firefox
        firefox
        chromium*
        """,
    )

    patterns = security_policy.reload_security_patterns()

    assert patterns.count("firefox") == 1
    assert patterns.count("chromium*") == 1


def test_patterns_are_cached_until_reload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    policy_path = _write_policy(tmp_path, "first-browser\n")

    security_policy.reload_security_patterns()

    assert security_policy.is_user_security_package("first-browser")

    policy_path.write_text("second-browser\n", encoding="utf-8")

    # Cache should still contain the first version.
    assert security_policy.is_user_security_package("first-browser")
    assert not security_policy.is_user_security_package("second-browser")

    security_policy.reload_security_patterns()

    assert not security_policy.is_user_security_package("first-browser")
    assert security_policy.is_user_security_package("second-browser")


def test_get_security_policy_path_uses_xdg_config_home(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert security_policy.get_security_policy_path() == (
        tmp_path / "bodhi-update-manager" / "security-packages.conf"
    )
