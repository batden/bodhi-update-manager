"""Tests for preferences storage and first-run logic."""

from __future__ import annotations

import os
import pytest

from bodhi_update.prefs import DEFAULT_PREFS, PreferencesStore


def test_show_welcome_defaults_to_false() -> None:
    """The default preference for show_welcome must be False."""
    assert DEFAULT_PREFS["show_welcome"] is False


def test_first_run_flow(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the complete first-run detection and marker file creation flow."""
    # Isolate XDG_CONFIG_HOME to a temporary path.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    store = PreferencesStore(app_name="test-update-manager")

    # The marker file should not exist initially, meaning it's the first run.
    assert store.is_first_run() is True

    marker_path = store.first_run_marker_path()
    assert os.path.basename(marker_path) == "first-run"
    assert "test-update-manager" in marker_path

    # Mark the first run as done.
    assert store.mark_first_run_done() is True

    # Now the marker file should exist, meaning it is no longer the first run.
    assert store.is_first_run() is False
    assert os.path.exists(marker_path)
    assert os.path.getsize(marker_path) == 0  # Should be empty
