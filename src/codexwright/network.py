"""A request-scoped CONNECT relay to pinned model endpoints, never an open proxy."""

import ipaddress
import re
import select
import socket
import socketserver
import threading
import time
from contextlib import contextmanager

from .errors import CodexwrightError


@contextmanager
def model_network(endpoints):
    ports, destinations = [], {}
    for item in endpoints or []:
        if type(item) is int and 1 <= item <= 65535:
            ports.append(item)
            continue
        try:
            host, port, addresses = item["host"], item["port"], item["addresses"]
            if type(port) is not int or not 1 <= port <= 65535 or not isinstance(host, str) or not re.fullmatch(r"[a-zA-Z0-9.:-]+", host):
                raise ValueError("Invalid endpoint authority")
            if not isinstance(addresses, (list, tuple)) or not 1 <= len(addresses) <= 16:
                raise ValueError("Invalid endpoint pins")
            pins = [ipaddress.ip_address(address) for address in addresses]
            if any(not pin.is_global or "%" in str(pin) for pin in pins):
                raise ValueError("Non-public endpoint pin")
            authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
            if ":" in host:
                ipaddress.IPv6Address(host)
            if authority in destinations:
                raise ValueError("Duplicate endpoint authority")
            destinations[authority] = {"port": port, "addresses": [str(pin) for pin in pins]}
        except (KeyError, TypeError, ValueError) as exc:
            raise CodexwrightError("unsafe_model_endpoint", "Relay requires explicit ports and public numeric endpoint pins") from exc
    if not destinations:
        yield ports, {}
        return

    class Tunnel(socketserver.StreamRequestHandler):
        # Do not prefetch TLS bytes that follow CONNECT headers in the same write.
        rbufsize = 0

        def handle(self):
            self.connection.settimeout(15)
            request = self.rfile.readline(8193)
            if len(request) > 8192:
                return
            parts = request.decode("ascii", errors="replace").strip().split()
            target = destinations.get(parts[1]) if len(parts) == 3 and parts[0] == "CONNECT" and parts[2] in {"HTTP/1.0", "HTTP/1.1"} else None
            header_bytes = 0
            while True:
                line = self.rfile.readline(8193)
                header_bytes += len(line)
                if not line or header_bytes > 32768:
                    return
                if line == b"\r\n":
                    break
            if target is None:
                self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                return
            upstream = None
            for address in target["addresses"]:
                if self.server.stopped.is_set():
                    return
                try:
                    upstream = socket.create_connection((address, target["port"]), timeout=5)
                    break
                except OSError:
                    continue
            if upstream is None:
                self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                return
            try:
                with upstream:
                    with self.server.lock:
                        if self.server.stopped.is_set():
                            return
                        self.server.upstreams.add(upstream)
                    self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    self.wfile.flush()
                    deadline = time.monotonic() + 600
                    transferred = 0
                    while not self.server.stopped.is_set() and time.monotonic() < deadline and transferred < 100000000:
                        readable, _, _ = select.select([self.connection, upstream], [], [], 15)
                        if not readable:
                            continue
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                return
                            transferred += len(data)
                            (upstream if source is self.connection else self.connection).sendall(data)
            finally:
                with self.server.lock:
                    self.server.upstreams.discard(upstream)

    class Relay(socketserver.ThreadingTCPServer):
        allow_reuse_address = False

        def __init__(self, *args):
            self.lock = threading.Lock()
            self.stopped = threading.Event()
            self.clients, self.upstreams = set(), set()
            super().__init__(*args)

        def process_request(self, request, client_address):
            with self.lock:
                if self.stopped.is_set() or len(self.clients) >= 16:
                    self.shutdown_request(request)
                    return
                self.clients.add(request)
            try:
                super().process_request(request, client_address)
            except BaseException:
                with self.lock:
                    self.clients.discard(request)
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                with self.lock:
                    self.clients.discard(request)

        def handle_error(self, request, client_address):
            # Endpoint failures carry no request body or authentication into logs.
            pass

    server = Relay(("127.0.0.1", 0), Tunnel)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    port = server.server_address[1]
    proxy = f"http://127.0.0.1:{port}"
    try:
        yield [*ports, port], {"HTTPS_PROXY": proxy, "HTTP_PROXY": proxy, "ALL_PROXY": proxy, "NO_PROXY": "localhost,127.0.0.1,::1"}
    finally:
        server.stopped.set()
        server.shutdown()
        with server.lock:
            connections = list(server.clients | server.upstreams)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        server.server_close()
        thread.join(timeout=2)
