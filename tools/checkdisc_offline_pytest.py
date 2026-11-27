"""Run pytest without sockets, respecting the checkdisc card's no-server rule.

Tests that attempt to bind/listen/connect are explicitly skipped, never passed.
No test or production validator is changed. Remove this harness when local test
servers have been authorized, and use python -m pytest -q directly instead.
"""
from pathlib import Path
import socket
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def no_socket(*args, **kwargs):
    raise unittest.SkipTest('task card hard rule: no network or servers')


socket.socket.bind = no_socket
socket.socket.listen = no_socket
socket.socket.connect = no_socket
socket.socket.connect_ex = no_socket

if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main(['-q', *sys.argv[1:]]))
