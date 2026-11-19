"""Keep simulated drives and WebUI state independent across pytest workers."""

import pytest


@pytest.fixture(autouse=True)
def private_user_state(tmp_path, monkeypatch):
    # Tests that share a real cross-process lock can still override this root.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user-state"))
