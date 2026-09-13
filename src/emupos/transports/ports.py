"""Is a local port free? Used by `emupos doctor` before the simulator opens anything."""

import socket
import sys


def tcp_port_free(host: str, port: int) -> bool:
    """True when `emupos run` could listen on `host`:`port` right now."""
    return _bindable(host, port, socket.SOCK_STREAM)


def udp_port_free(host: str, port: int) -> bool:
    return _bindable(host, port, socket.SOCK_DGRAM)


def _bindable(host: str, port: int, kind: socket.SocketKind) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, kind) as probe:
        if kind == socket.SOCK_STREAM and sys.platform != "win32":
            # Same as the TCP listener: a port in TIME_WAIT after a clean shutdown is free to reuse.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host.strip("[]"), port))
        except OSError:
            return False
    return True
