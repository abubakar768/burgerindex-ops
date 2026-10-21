"""scripts/local_sandbox.py must not strand processes or ports.

The crawl target used to be a `python -m http.server` child. A child outlives a
parent that is killed, so a stopped `serve` left it holding port 8777, and the
next run's server silently failed to bind and the spiders saw its 404s.
"""
import importlib.util
import pathlib
import socket
import urllib.request

import psutil
import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "local_sandbox.py"


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("local_sandbox_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "hello.txt").write_text("hi")
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    monkeypatch.setattr(mod, "TARGET_PORT", free_port())
    monkeypatch.setattr(mod, "DASH_PORT", free_port())
    return mod


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_services_are_threads_not_children(sandbox):
    """A thread dies with the process, even under SIGKILL; a child does not."""
    before = {p.pid for p in psutil.Process().children(recursive=True)}
    servers = sandbox.start_services()
    try:
        after = {p.pid for p in psutil.Process().children(recursive=True)}
        assert after == before, "start_services spawned a child process"
        url = f"http://127.0.0.1:{sandbox.TARGET_PORT}/hello.txt"
        assert urllib.request.urlopen(url, timeout=5).read() == b"hi"
    finally:
        sandbox.stop_services(servers)

    # stop_services must release the port, not just stop answering on it. SO_REUSEADDR,
    # as every server sets, so a connection lingering in TIME_WAIT does not count:
    # this fails only if a socket is still listening.
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", sandbox.TARGET_PORT))


def test_a_busy_port_is_reported_not_swallowed(sandbox):
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", sandbox.TARGET_PORT))
        holder.listen()
        with pytest.raises(SystemExit) as exc:
            sandbox.start_services()
    message = str(exc.value)
    assert str(sandbox.TARGET_PORT) in message and "in use" in message
    assert "lsof" in message  # says how to find the holder
