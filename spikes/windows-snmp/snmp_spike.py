# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Windows SNMP spike (task 1.3): what does the Standard TCP/IP port monitor ask, and
which answers make a queue show ready, paper out, door open or offline?

Runs two fake printer endpoints on 127.0.0.1:
- UDP 161: a minimal SNMPv1/v2c GET/GETNEXT agent. Every request (version, community,
  PDU type, OIDs) and every reply is appended to a JSONL log.
- TCP 9100: a raw sink that saves each print job as spaced hex.

    uv run spikes/windows-snmp/snmp_spike.py --mode silent
    uv run spikes/windows-snmp/snmp_spike.py --mode nosuch
    uv run spikes/windows-snmp/snmp_spike.py --mode printer --state paper-out
    uv run spikes/windows-snmp/snmp_spike.py --self-test

Status values follow RFC 3805 section 2.2.13.2 (the hrDeviceStatus / hrPrinterStatus /
hrPrinterDetectedErrorState table) and the bit numbering of RFC 2790
hrPrinterDetectedErrorState: bit 0 is the most significant bit of the first octet, and
lowPaper=0, noPaper=1, lowToner=2, noToner=3, doorOpen=4, jammed=5, offline=6,
serviceRequested=7.

No third-party packages: BER is encoded and decoded by hand, for the handful of types
SNMP GET/GETNEXT needs. This is spike code; the product responder is task 10.3.
"""

import argparse
import asyncio
import json
import socket
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
JOB_IDLE_TIMEOUT = 30.0  # seconds without data before a print job is considered finished

# ---------------------------------------------------------------------------------------
# BER (ASN.1 Basic Encoding Rules), just enough for SNMP v1/v2c
# ---------------------------------------------------------------------------------------

INTEGER, OCTET_STRING, NULL, OBJECT_ID, SEQUENCE = 0x02, 0x04, 0x05, 0x06, 0x30
TIMETICKS = 0x43
NO_SUCH_OBJECT, NO_SUCH_INSTANCE, END_OF_MIB_VIEW = 0x80, 0x81, 0x82  # v2c only
GET, GETNEXT, RESPONSE = 0xA0, 0xA1, 0xA2
PDU_NAMES = {
    0xA0: "get",
    0xA1: "getnext",
    0xA2: "response",
    0xA3: "set",
    0xA4: "trap-v1",
    0xA5: "getbulk",
    0xA6: "inform",
    0xA7: "trap-v2",
    0xA8: "report",
}
VERSION_NAMES = {0: "v1", 1: "v2c", 3: "v3"}
NO_SUCH_NAME = 2  # v1 error-status


def encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    body = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + encode_length(len(content)) + content


def int_content(value: int) -> bytes:
    """Minimal two's-complement bytes."""
    bits = value.bit_length() if value >= 0 else (~value).bit_length()
    return value.to_bytes(bits // 8 + 1, "big", signed=True)


def encode_int(value: int) -> bytes:
    return tlv(INTEGER, int_content(value))


def oid_content(dotted: str) -> bytes:
    arcs = [int(part) for part in dotted.split(".")]
    sub_ids = [40 * arcs[0] + arcs[1], *arcs[2:]]  # the first two arcs share one sub-id
    body = bytearray()
    for sub_id in sub_ids:  # base 128, high bit set on every byte but the last
        chunk = [sub_id & 0x7F]
        sub_id >>= 7
        while sub_id:
            chunk.append(0x80 | (sub_id & 0x7F))
            sub_id >>= 7
        body.extend(reversed(chunk))
    return bytes(body)


def encode_oid(dotted: str) -> bytes:
    return tlv(OBJECT_ID, oid_content(dotted))


def read_tlv(data: bytes, pos: int) -> tuple[int, bytes, int]:
    """Return (tag, content, position after the element). Raises ValueError/IndexError."""
    tag = data[pos]
    first = data[pos + 1]
    pos += 2
    if first < 0x80:
        length = first
    else:
        size = first & 0x7F
        if not 1 <= size <= 4:
            raise ValueError(f"unsupported length form 0x{first:02x}")
        length = int.from_bytes(data[pos : pos + size], "big")
        pos += size
    end = pos + length
    if end > len(data):
        raise ValueError("truncated element")
    return tag, data[pos:end], end


def read_children(content: bytes) -> list[tuple[int, bytes]]:
    items, pos = [], 0
    while pos < len(content):
        tag, value, pos = read_tlv(content, pos)
        items.append((tag, value))
    return items


def decode_int(content: bytes) -> int:
    return int.from_bytes(content, "big", signed=True)


def decode_oid(content: bytes) -> str:
    sub_ids, value = [], 0
    for byte in content:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            sub_ids.append(value)
            value = 0
    first = sub_ids[0]
    head = [0, first] if first < 40 else [1, first - 40] if first < 80 else [2, first - 80]
    return ".".join(str(arc) for arc in head + sub_ids[1:])


def oid_key(dotted: str) -> tuple[int, ...]:
    return tuple(int(part) for part in dotted.split("."))


# ---------------------------------------------------------------------------------------
# SNMP messages
# ---------------------------------------------------------------------------------------


def decode_message(packet: bytes) -> dict:
    """Decode an SNMP message. v1/v2c get full PDU details; other versions only a version."""
    tag, body, end = read_tlv(packet, 0)
    if tag != SEQUENCE or end != len(packet):
        raise ValueError("not a single BER SEQUENCE")
    items = read_children(body)
    if items[0][0] != INTEGER:
        raise ValueError("version is not an INTEGER")
    version = decode_int(items[0][1])
    if version not in (0, 1):
        return {"version": version}
    (community_tag, community), (pdu_tag, pdu) = items[1], items[2]
    if community_tag != OCTET_STRING:
        raise ValueError("community is not an OCTET STRING")
    request_id, error_status, error_index, (_, varbind_list) = read_children(pdu)
    varbinds = []
    for _, varbind in read_children(varbind_list):
        (oid_tag, oid), (value_tag, value) = read_children(varbind)
        if oid_tag != OBJECT_ID:
            raise ValueError("varbind name is not an OID")
        varbinds.append((decode_oid(oid), value_tag, value))
    return {
        "version": version,
        "community": community,
        "pdu_type": pdu_tag,
        "request_id": decode_int(request_id[1]),
        "error_status": decode_int(error_status[1]),
        "error_index": decode_int(error_index[1]),
        "varbinds": varbinds,
    }


def encode_message(
    version: int,
    community: bytes,
    pdu_type: int,
    request_id: int,
    varbinds: list[tuple[str, int, bytes]],
    error_status: int = 0,
    error_index: int = 0,
) -> bytes:
    """Encode a message; each varbind is (oid, value tag, value content)."""
    varbind_list = b"".join(
        tlv(SEQUENCE, encode_oid(oid) + tlv(value_tag, value)) for oid, value_tag, value in varbinds
    )
    pdu = (
        encode_int(request_id)
        + encode_int(error_status)
        + encode_int(error_index)
        + tlv(SEQUENCE, varbind_list)
    )
    return tlv(SEQUENCE, encode_int(version) + tlv(OCTET_STRING, community) + tlv(pdu_type, pdu))


def value_content(tag: int, value: int | bytes | str) -> bytes:
    """Content bytes (no tag/length) for a MIB value."""
    if tag in (INTEGER, TIMETICKS):
        assert isinstance(value, int)
        return int_content(value)
    if tag == OBJECT_ID:
        assert isinstance(value, str)
        return oid_content(value)
    assert isinstance(value, bytes)
    return value


# ---------------------------------------------------------------------------------------
# The fake printer's MIB
# ---------------------------------------------------------------------------------------

# state: (hrDeviceStatus, hrPrinterStatus, first octet of hrPrinterDetectedErrorState)
# RFC 3805 2.2.13.2 table; bits per RFC 2790 (MSB of first octet = bit 0).
STATES = {
    "ready": (2, 3, 0x00),  # running, idle, nothing set
    "low-paper": (3, 3, 0x80),  # warning, idle, lowPaper (bit 0)  "Non Critical Alert"
    "paper-out": (5, 1, 0x40),  # down, other, noPaper (bit 1)     "Critical Alert"
    "door-open": (5, 1, 0x08),  # down, other, doorOpen (bit 4)    "Critical Alert"
    "offline": (5, 1, 0x02),  # down, other, offline (bit 6)       "Off-line"
}
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
HR_DEVICE_TYPE = "1.3.6.1.2.1.25.3.2.1.2"  # + .index
HR_DEVICE_DESCR = "1.3.6.1.2.1.25.3.2.1.3"
HR_DEVICE_STATUS = "1.3.6.1.2.1.25.3.2.1.5"
HR_PRINTER_STATUS = "1.3.6.1.2.1.25.3.5.1.1"
HR_PRINTER_ERROR_STATE = "1.3.6.1.2.1.25.3.5.1.2"
HR_DEVICE_PRINTER = "1.3.6.1.2.1.25.3.1.5"  # hrDevicePrinter { hrDeviceTypes 5 }
EXAMPLE_ENTERPRISE = "1.3.6.1.4.1.32473"  # IANA example enterprise number (RFC 5612)

Mib = dict[str, tuple[int, int | bytes | str]]  # oid -> (value tag, value)


def printer_rows(index: int, state: str, error_octets: int) -> Mib:
    device_status, printer_status, error_bits = STATES[state]
    error_state = bytes([error_bits]) + bytes(error_octets - 1)
    return {
        f"{HR_DEVICE_TYPE}.{index}": (OBJECT_ID, HR_DEVICE_PRINTER),
        f"{HR_DEVICE_DESCR}.{index}": (OCTET_STRING, f"emupos spike printer {index}".encode()),
        f"{HR_DEVICE_STATUS}.{index}": (INTEGER, device_status),
        f"{HR_PRINTER_STATUS}.{index}": (INTEGER, printer_status),
        f"{HR_PRINTER_ERROR_STATE}.{index}": (OCTET_STRING, error_state),
    }


def build_mib(community: str, uptime_ticks: int, config: argparse.Namespace) -> Mib:
    """The objects answered for one request. Empty in `nosuch` mode."""
    if config.mode != "printer":
        return {}
    mib: Mib = {
        SYS_DESCR: (OCTET_STRING, b"emupos SNMP spike"),
        SYS_OBJECT_ID: (OBJECT_ID, EXAMPLE_ENTERPRISE),
        SYS_UPTIME: (TIMETICKS, uptime_ticks),
    }
    state = config.community_states.get(community, config.state)
    mib |= printer_rows(config.index, state, config.error_octets)
    for index, index_state in config.index_states.items():
        mib |= printer_rows(index, index_state, config.error_octets)
    return mib


def answer(request: dict, mib: Mib) -> tuple[list[tuple[str, int, bytes]], int, int]:
    """Varbinds, error-status and error-index for a GET or GETNEXT, per RFC 1157 / RFC 3416."""
    is_v1 = request["version"] == 0
    ordered = sorted(mib, key=oid_key)
    result = []
    for position, (oid, _, _) in enumerate(request["varbinds"], start=1):
        if request["pdu_type"] == GET:
            found = oid if oid in mib else None
            missing_tag = NO_SUCH_OBJECT
        else:
            found = next((o for o in ordered if oid_key(o) > oid_key(oid)), None)
            missing_tag = END_OF_MIB_VIEW
        if found is None:
            if is_v1:  # v1 has no exception values: the whole request fails
                echoed = [(o, tag, value) for o, tag, value in request["varbinds"]]
                return echoed, NO_SUCH_NAME, position
            result.append((oid, missing_tag, b""))
        else:
            tag, value = mib[found]
            result.append((found, tag, value_content(tag, value)))
    return result, 0, 0


# ---------------------------------------------------------------------------------------
# Logging and the servers
# ---------------------------------------------------------------------------------------


def log_line(path: Path, record: dict) -> None:
    record = {"time": datetime.now(UTC).isoformat(timespec="milliseconds"), **record}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")
    print(json.dumps(record))


def describe_varbinds(varbinds: list[tuple[str, int, bytes]]) -> list[list]:
    return [[oid, f"0x{tag:02x}", value.hex(" ")] for oid, tag, value in varbinds]


def handle_datagram(packet: bytes, sender: str, config: argparse.Namespace) -> bytes | None:
    """Log one UDP packet and return the reply bytes, or None to stay silent."""
    record: dict = {"kind": "snmp", "from": sender, "mode": config.mode, "state": config.state}
    try:
        request = decode_message(packet)
    except (ValueError, IndexError) as exc:
        log_line(config.log, record | {"malformed": str(exc), "hex": packet.hex(" ")})
        return None
    version = request["version"]
    record["version"] = VERSION_NAMES.get(version, version)
    if version not in (0, 1):
        log_line(config.log, record | {"ignored": "unsupported version", "hex": packet.hex(" ")})
        return None
    community = request["community"].decode("latin-1")
    pdu_name = PDU_NAMES.get(request["pdu_type"], hex(request["pdu_type"]))
    record |= {
        "community": community,
        "pdu": pdu_name,
        "request_id": request["request_id"],
        "oids": [oid for oid, _, _ in request["varbinds"]],
    }
    if config.mode == "silent" or request["pdu_type"] not in (GET, GETNEXT):
        log_line(config.log, record | {"replied": False})
        return None
    uptime_ticks = int((time.monotonic() - config.started) * 100)
    mib = build_mib(community, uptime_ticks, config)
    varbinds, error_status, error_index = answer(request, mib)
    reply = encode_message(
        version,
        request["community"],
        RESPONSE,
        request["request_id"],
        varbinds,
        error_status,
        error_index,
    )
    log_line(
        config.log,
        record
        | {
            "replied": True,
            "error_status": error_status,
            "error_index": error_index,
            "response": describe_varbinds(varbinds),
        },
    )
    return reply


class SnmpProtocol(asyncio.DatagramProtocol):
    def __init__(self, config: argparse.Namespace) -> None:
        self.config = config
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        assert isinstance(transport, asyncio.DatagramTransport)
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        reply = handle_datagram(data, f"{addr[0]}:{addr[1]}", self.config)
        if reply is not None and self.transport is not None:
            self.transport.sendto(reply, addr)

    def error_received(self, exc: Exception) -> None:
        # Windows reports ICMP "port unreachable" from an earlier reply as an error here.
        print(f"UDP error (ignored): {exc!r}")


def spaced_hex(data: bytes) -> str:
    return "\n".join(data[i : i + 16].hex(" ") for i in range(0, len(data), 16)) + "\n"


async def receive_job(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, config: argparse.Namespace
) -> None:
    peer = writer.get_extra_info("peername")
    chunks, ended_by = [], "close"
    try:
        while chunk := await asyncio.wait_for(reader.read(65536), JOB_IDLE_TIMEOUT):
            chunks.append(chunk)
    except TimeoutError:
        ended_by = f"idle {JOB_IDLE_TIMEOUT:.0f}s"
    except ConnectionError as exc:
        ended_by = repr(exc)
    finally:
        writer.close()
    data = b"".join(chunks)
    config.jobs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    path = config.jobs / f"job-{stamp}.hex"
    path.write_text(spaced_hex(data), encoding="utf-8")
    log_line(
        config.log,
        {
            "kind": "tcp-job",
            "from": str(peer),
            "bytes": len(data),
            "ended_by": ended_by,
            "file": path.name,
        },
    )


PORT_161_HELP = """\
Could not bind UDP {host}:{port}: {exc}
On Windows the usual cause is the "SNMP Service". Check and stop it in an admin PowerShell:
    Get-Service SNMP
    Get-NetUDPEndpoint -LocalPort {port} | Select-Object LocalAddress, OwningProcess
    Stop-Service SNMP
On macOS/Linux, ports below 1024 need root: use --port 1161 for local testing."""


async def serve(config: argparse.Namespace) -> int:
    loop = asyncio.get_running_loop()
    try:
        udp, _ = await loop.create_datagram_endpoint(
            lambda: SnmpProtocol(config), local_addr=(config.host, config.port)
        )
    except OSError as exc:
        print(PORT_161_HELP.format(host=config.host, port=config.port, exc=exc), file=sys.stderr)
        return 1
    try:
        tcp = await asyncio.start_server(
            lambda r, w: receive_job(r, w, config), config.host, config.tcp_port
        )
    except OSError as exc:
        udp.close()
        print(f"Could not listen on TCP {config.host}:{config.tcp_port}: {exc}", file=sys.stderr)
        return 1
    state = f", state {config.state}" if config.mode == "printer" else ""
    print(f"SNMP on udp {config.host}:{config.port} (mode {config.mode}{state})")
    print(f"Print jobs on tcp {config.host}:{config.tcp_port} -> {config.jobs}")
    print(f"Log: {config.log}    Stop with Ctrl+C.")
    deadline = time.monotonic() + config.duration if config.duration else None
    try:
        while deadline is None or time.monotonic() < deadline:
            await asyncio.sleep(1)  # short sleeps so Ctrl+C is noticed promptly on Windows
    finally:
        udp.close()
        tcp.close()
        await asyncio.wait_for(tcp.wait_closed(), 5)
    return 0


# ---------------------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------------------


def self_test_config(**overrides: object) -> argparse.Namespace:
    tmp = Path(tempfile.mkdtemp(prefix="snmp-spike-"))
    config = parse_args(["--mode", "printer", "--log", str(tmp / "log.jsonl"), "--jobs", str(tmp)])
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def roundtrip(
    config: argparse.Namespace,
    version: int,
    pdu_type: int,
    oids: list[str],
    community: bytes = b"public",
) -> dict:
    request = encode_message(version, community, pdu_type, 4242, [(oid, NULL, b"") for oid in oids])
    decoded = decode_message(request)
    assert decoded["varbinds"] == [(oid, NULL, b"") for oid in oids], decoded
    assert decoded["community"] == community and decoded["request_id"] == 4242
    reply = handle_datagram(request, "self-test", config)
    assert reply is not None
    response = decode_message(reply)
    assert response["pdu_type"] == RESPONSE and response["request_id"] == 4242
    assert response["version"] == version
    return response


def self_test() -> None:
    # BER primitives against hand-checked bytes
    assert encode_oid("1.3.6.1.2.1.1.1.0") == bytes.fromhex("06 08 2b 06 01 02 01 01 01 00")
    assert encode_oid("1.3.6.1.4.1.32473") == bytes.fromhex("06 08 2b 06 01 04 01 81 fd 59")
    assert decode_oid(bytes.fromhex("2b 06 01 04 01 81 fd 59")) == "1.3.6.1.4.1.32473"
    for value, expected in [
        (0, "02 01 00"),
        (127, "02 01 7f"),
        (128, "02 02 00 80"),
        (-1, "02 01 ff"),
        (-129, "02 02 ff 7f"),
    ]:
        assert encode_int(value) == bytes.fromhex(expected), value
        assert decode_int(encode_int(value)[2:]) == value
    assert encode_length(300) == bytes.fromhex("82 01 2c")
    assert read_tlv(tlv(OCTET_STRING, bytes(300)), 0)[1] == bytes(300)

    status_oids = [f"{HR_DEVICE_STATUS}.1", f"{HR_PRINTER_STATUS}.1", f"{HR_PRINTER_ERROR_STATE}.1"]
    expected = {
        "ready": (2, 3, "00"),
        "low-paper": (3, 3, "80"),
        "paper-out": (5, 1, "40"),
        "door-open": (5, 1, "08"),
        "offline": (5, 1, "02"),
    }
    for state, (device, printer, bits) in expected.items():
        for version in (0, 1):
            response = roundtrip(self_test_config(state=state), version, GET, status_oids)
            values = [v for _, _, v in response["varbinds"]]
            assert decode_int(values[0]) == device and decode_int(values[1]) == printer, state
            assert values[2].hex() == bits, (state, values[2])

    config = self_test_config()
    # v2c GETNEXT walk from the root visits every object in order and ends with endOfMibView
    oid, walked = "1.3.6.1", []
    while True:
        ((found, tag, _),) = roundtrip(config, 1, GETNEXT, [oid])["varbinds"]
        if tag == END_OF_MIB_VIEW:
            break
        walked.append(found)
        oid = found
    assert walked == sorted(build_mib("public", 0, config), key=oid_key), walked
    assert walked[0] == SYS_DESCR and walked[-1] == f"{HR_PRINTER_ERROR_STATE}.1"

    # unknown objects: v2c exception value, v1 noSuchName with error-index
    unknown = "1.3.6.1.2.1.43.11.1.1.9.1.1"
    ((_, tag, _),) = roundtrip(config, 1, GET, [unknown])["varbinds"]
    assert tag == NO_SUCH_OBJECT
    v1 = roundtrip(config, 0, GET, [SYS_DESCR, unknown])
    assert (v1["error_status"], v1["error_index"]) == (NO_SUCH_NAME, 2)

    # nosuch mode, per-queue overrides, two-octet error state
    ((_, tag, _),) = roundtrip(self_test_config(mode="nosuch"), 1, GET, [SYS_DESCR])["varbinds"]
    assert tag == NO_SUCH_OBJECT
    per_queue = self_test_config(
        community_states={"back": "offline"}, index_states={2: "door-open"}
    )
    ((_, _, bits),) = roundtrip(per_queue, 1, GET, [f"{HR_PRINTER_ERROR_STATE}.1"], b"back")[
        "varbinds"
    ]
    assert bits == b"\x02"
    ((_, _, bits),) = roundtrip(per_queue, 1, GET, [f"{HR_PRINTER_ERROR_STATE}.2"])["varbinds"]
    assert bits == b"\x08"
    ((_, _, bits),) = roundtrip(
        self_test_config(state="paper-out", error_octets=2), 1, GET, [f"{HR_PRINTER_ERROR_STATE}.1"]
    )["varbinds"]
    assert bits == b"\x40\x00"

    # silence: silent mode, SET, malformed packets, v3
    assert (
        handle_datagram(
            encode_message(1, b"public", GET, 1, [(SYS_DESCR, NULL, b"")]),
            "t",
            self_test_config(mode="silent"),
        )
        is None
    )
    assert (
        handle_datagram(
            encode_message(1, b"public", 0xA3, 1, [(SYS_DESCR, OCTET_STRING, b"x")]), "t", config
        )
        is None
    )
    assert handle_datagram(b"\x30\x05\x02\x01", "t", config) is None
    assert handle_datagram(b"garbage", "t", config) is None
    assert handle_datagram(tlv(SEQUENCE, encode_int(3) + tlv(SEQUENCE, b"")), "t", config) is None

    asyncio.run(live_self_test(self_test_config()))
    print("\nSELF-TEST PASSED")


async def live_self_test(config: argparse.Namespace) -> None:
    """Real sockets on free loopback ports: one UDP GET and one TCP job."""
    loop = asyncio.get_running_loop()
    udp, _ = await loop.create_datagram_endpoint(
        lambda: SnmpProtocol(config), local_addr=("127.0.0.1", 0)
    )
    port = udp.get_extra_info("sockname")[1]
    request = encode_message(1, b"public", GET, 7, [(f"{HR_DEVICE_STATUS}.1", NULL, b"")])
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(2)
        client.sendto(request, ("127.0.0.1", port))
        reply = await asyncio.to_thread(client.recv, 2048)
    udp.close()
    ((_, _, value),) = decode_message(reply)["varbinds"]
    assert decode_int(value) == 2

    server = await asyncio.start_server(lambda r, w: receive_job(r, w, config), "127.0.0.1", 0)
    tcp_port = server.sockets[0].getsockname()[1]
    _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", tcp_port), 2)
    writer.write(bytes.fromhex("1b 40 48 69 0a 1d 56 00"))
    await writer.drain()
    writer.close()
    for _ in range(50):
        if files := list(config.jobs.glob("job-*.hex")):
            break
        await asyncio.sleep(0.05)
    server.close()
    await asyncio.wait_for(server.wait_closed(), 5)
    assert files and files[0].read_text() == "1b 40 48 69 0a 1d 56 00\n", files


# ---------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------


def key_state(text: str) -> tuple[str, str]:
    key, _, state = text.partition("=")
    if state not in STATES:
        raise argparse.ArgumentTypeError(f"expected KEY=STATE with STATE in {sorted(STATES)}")
    return key, state


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["silent", "nosuch", "printer"], default="printer")
    parser.add_argument("--state", choices=sorted(STATES), default="ready")
    parser.add_argument(
        "--index", type=int, default=1, help="hrDeviceIndex to answer (Add-PrinterPort -SNMP)"
    )
    parser.add_argument(
        "--index-state",
        action="append",
        type=key_state,
        default=[],
        metavar="N=STATE",
        help="also answer index N with STATE (repeatable)",
    )
    parser.add_argument(
        "--community-state",
        action="append",
        type=key_state,
        default=[],
        metavar="NAME=STATE",
        help="use STATE for requests with community NAME (repeatable)",
    )
    parser.add_argument(
        "--error-octets",
        type=int,
        choices=[1, 2],
        default=1,
        help="length of hrPrinterDetectedErrorState",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=161, help="UDP port for SNMP")
    parser.add_argument("--tcp-port", type=int, default=9100, help="TCP port for print jobs")
    parser.add_argument(
        "--duration", type=float, default=0, help="stop after N seconds (0 = until Ctrl+C)"
    )
    parser.add_argument("--log", type=Path, default=HERE / "snmp-log.jsonl")
    parser.add_argument("--jobs", type=Path, default=HERE / "jobs")
    parser.add_argument("--self-test", action="store_true")
    config = parser.parse_args(argv)
    config.index_states = {int(k): v for k, v in config.index_state}
    config.community_states = dict(config.community_state)
    config.started = time.monotonic()
    return config


def main() -> int:
    config = parse_args()
    if config.self_test:
        self_test()
        return 0
    try:
        return asyncio.run(serve(config))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
