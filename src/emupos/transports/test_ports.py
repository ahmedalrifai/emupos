import socket

from emupos.transports.ports import tcp_port_free, udp_port_free


def test_tcp_port_in_use_is_not_free() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        assert not tcp_port_free("127.0.0.1", port)
    assert tcp_port_free("127.0.0.1", port)


def test_udp_port_in_use_is_not_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        assert not udp_port_free("127.0.0.1", port)
    assert udp_port_free("127.0.0.1", port)
