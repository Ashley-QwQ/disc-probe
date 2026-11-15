"""Portable source-provenance hashes, distinct from exact artifact checksums.

Only the extensions in TEXT_SUFFIXES (case insensitive) normalize CRLF to LF.
No decoding, whitespace trimming, BOM removal or lone-CR conversion is done.
All other extensions, including .npz, .npy, .bin and .gz, hash original bytes.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

TEXT_SUFFIXES = frozenset({
    '.py', '.json', '.md', '.txt', '.csv', '.js', '.mjs', '.ts', '.tsx',
    '.jsx', '.css', '.html', '.htm', '.svg', '.xml', '.toml', '.yaml',
    '.yml', '.ini', '.cfg', '.rst', '.sh', '.ps1', '.bat', '.cmd',
})


def content_sha256(data: bytes, suffix: str) -> str:
    """Hash in-memory file content, using its logical suffix (e.g. '.json')."""
    if suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: str | Path) -> str:
    """Hash a file with the same extension policy; stream binary/unknown files."""
    path = Path(path)
    if path.suffix.lower() in TEXT_SUFFIXES:
        return content_sha256(path.read_bytes(), path.suffix)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()
