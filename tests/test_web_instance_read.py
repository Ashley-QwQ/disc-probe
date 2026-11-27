"""Reading the instance record while Windows replaces or deletes it."""
import pytest

from discprobe import web_instance


class Flaky:
    def __init__(self, failures, winerror=5, data=b'{"pid": 1}'):
        self.failures, self.winerror, self.data, self.calls = failures, winerror, data, 0

    def read_bytes(self):
        self.calls += 1
        if self.calls <= self.failures:
            error = PermissionError(13, "Permission denied")
            error.winerror = self.winerror
            raise error
        return self.data


@pytest.mark.parametrize("winerror", [5, 32])
def test_transient_access_denied_is_read_again(winerror):
    path = Flaky(3, winerror)
    assert web_instance._read(path) == {"pid": 1}
    assert path.calls == 4


def test_lasting_or_other_permission_errors_still_raise():
    with pytest.raises(PermissionError):
        web_instance._read(Flaky(50))
    other = Flaky(1, winerror=None)
    with pytest.raises(PermissionError):
        web_instance._read(other)
    assert other.calls == 1
