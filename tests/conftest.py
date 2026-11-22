"""Keep simulated drives and WebUI state independent across pytest workers."""

import pytest


@pytest.fixture(autouse=True)
def private_user_state(tmp_path, monkeypatch):
    # Tests that share a real cross-process lock can still override this root.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user-state"))
    # Works default to ./works beside ./results, i.e. the checkout a person's web page serves.
    # CLI burns in tests (mocked writes included) file records there unless this is set.
    monkeypatch.setenv("DISCPROBE_HOME", str(tmp_path / "discprobe-home"))
