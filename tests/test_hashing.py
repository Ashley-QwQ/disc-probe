"""Source hashes tolerate checkout EOLs without masking other byte changes."""
import hashlib

import pytest

from discprobe.hashing import TEXT_SUFFIXES, content_sha256, file_sha256


@pytest.mark.parametrize('suffix', sorted(TEXT_SUFFIXES) + ['.PY', '.JSON'])
def test_text_lf_and_crlf_have_the_same_hash(tmp_path, suffix):
    lf = b'first line\nUTF-8: \xe4\xb8\xad\xe6\x96\x87\nlast line\n'
    path = tmp_path / ('input' + suffix)
    path.write_bytes(lf)
    expected = hashlib.sha256(lf).hexdigest()
    assert file_sha256(path) == expected
    path.write_bytes(lf.replace(b'\n', b'\r\n'))
    assert file_sha256(path) == expected
    assert content_sha256(path.read_bytes(), suffix) == expected


@pytest.mark.parametrize('suffix', ['.npz', '.npy', '.bin', '.gz', '.pdf', '.unknown', ''])
def test_binary_and_unknown_extensions_hash_original_bytes(tmp_path, suffix):
    path = tmp_path / ('input' + suffix)
    # Include a CRLF crossing the binary stream's chunk boundary.
    data = b'\x00' * ((1 << 20) - 1) + b'\r\n\xff\n'
    path.write_bytes(data)
    assert file_sha256(path) == content_sha256(data, suffix) == hashlib.sha256(data).hexdigest()
    path.write_bytes(data.replace(b'\r\n', b'\n'))
    assert file_sha256(path) != hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize('changed', [b'a\rb\n', b'a\nb \n', b'\xef\xbb\xbfa\nb\n', b'a\nc\n'])
def test_text_hash_preserves_changes_other_than_crlf(tmp_path, changed):
    path = tmp_path / 'input.json'
    path.write_bytes(changed)
    assert file_sha256(path) != content_sha256(b'a\nb\n', '.json')


def test_text_hash_normalizes_mixed_line_endings():
    assert content_sha256(b'a\r\nb\nc\r\n', '.json') == content_sha256(b'a\nb\nc\n', '.json')


@pytest.mark.parametrize('newline', [b'\n', b'\r\n'])
def test_decompressed_regression_json_uses_text_policy(monkeypatch, newline):
    from tools import focal_regression

    raw = focal_regression.fixture_bytes().replace(b'\r\n', b'\n')
    expected = focal_regression.calculate()
    monkeypatch.setattr(focal_regression, 'fixture_bytes', lambda: raw.replace(b'\n', newline))
    assert focal_regression.calculate() == expected
