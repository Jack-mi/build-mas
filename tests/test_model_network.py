import socket
import threading

import pytest

from build_mas.errors import BuildMasError
from build_mas.network import model_network


def test_relay_only_connects_to_pinned_host_and_numeric_destination(monkeypatch):
    upstream, remote = socket.socketpair()
    closed = threading.Event()

    def echo():
        with remote:
            remote.sendall(remote.recv(100))
            assert remote.recv(100) == b""
        closed.set()

    thread = threading.Thread(target=echo)
    thread.start()
    real_connect = socket.create_connection
    calls = []

    def connect(address, *args, **kwargs):
        if address[0] == "93.184.216.34":
            calls.append(address)
            return upstream
        return real_connect(address, *args, **kwargs)

    monkeypatch.setattr("build_mas.network.socket.create_connection", connect)
    with model_network([{"host": "model.example", "port": 443, "addresses": ["93.184.216.34"]}]) as (ports, env):
        assert env["HTTPS_PROXY"].startswith("http://127.0.0.1:")
        for request in (b"CONNECT evil.example:443 HTTP/1.1", b"GET model.example:443 HTTP/1.1", b"CONNECT model.example:443 INVALID"):
            with real_connect(("127.0.0.1", ports[-1]), timeout=2) as client:
                client.sendall(request + b"\r\n\r\n")
                assert b"403" in client.recv(100)
        assert calls == []
        client = real_connect(("127.0.0.1", ports[-1]), timeout=2)
        stream = client.makefile("rb", buffering=0)
        client.sendall(b"CONNECT model.example:443 HTTP/1.1\r\n\r\nSAFE")
        assert b"200" in stream.readline()
        assert stream.readline() == b"\r\n"
        assert stream.read(4) == b"SAFE"
        assert calls == [("93.184.216.34", 443)]
    assert client.recv(1) == b""
    stream.close()
    client.close()
    assert closed.wait(2)
    thread.join(timeout=2)
    assert not thread.is_alive()
    with pytest.raises(OSError):
        real_connect(("127.0.0.1", ports[-1]), timeout=1)


@pytest.mark.parametrize("endpoint", [True, 0, {"host": "model.example", "port": 443, "addresses": ["10.0.0.1"]}, {"host": "model.example", "port": 443, "addresses": ["model.example"]}, {"host": "model.example/path", "port": 443, "addresses": ["93.184.216.34"]}])
def test_relay_rejects_invalid_or_private_pins(endpoint):
    with pytest.raises(BuildMasError, match="public numeric"):
        with model_network([endpoint]):
            pytest.fail("Unsafe relay opened")


def test_relay_bounds_concurrent_clients_and_closes_partial_headers():
    clients = []
    try:
        with model_network([{"host": "model.example", "port": 443, "addresses": ["93.184.216.34"]}]) as (ports, _):
            for _ in range(16):
                client = socket.create_connection(("127.0.0.1", ports[-1]), timeout=2)
                client.sendall(b"CONNECT model.example:443 HTTP/1.1\r\n")
                clients.append(client)
            with socket.create_connection(("127.0.0.1", ports[-1]), timeout=2) as extra:
                assert extra.recv(1) == b""
        assert all(client.recv(1) == b"" for client in clients)
    finally:
        for client in clients:
            client.close()
