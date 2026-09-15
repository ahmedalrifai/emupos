"""Answers to the status polls of the Windows Standard TCP/IP port monitor (design D7). Pure.

A queue's port asks with SNMP v1: GETNEXT `1.3.6.1.4.1.2699.1.2` and GET `sysDescr.0` about
every 10 minutes, and one GET of hrDeviceStatus, hrPrinterStatus and
hrPrinterDetectedErrorState at the port's SNMP index (spike 1.3). `emupos setup print-queue` sets
that index to the printer's TCP port, so the index names the printer.

BER is encoded by hand for the few types GET and GETNEXT need.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal

from emupos.printer.printer import BLOCKING_FAULTS, PrinterFault

PORT = 161
PORT_IN_USE = (
    'UDP port 161 on 127.0.0.1 is in use, usually by the Windows "SNMP Service"; '
    "print queues will not show printer status until the port is free"
)
STOP_SNMP_SERVICE = (
    'stop the "SNMP Service" in a PowerShell opened with "Run as administrator": '
    "`Stop-Service SNMP; Set-Service SNMP -StartupType Disabled`"
)

INTEGER, OCTET_STRING, NULL, OBJECT_ID, SEQUENCE = 0x02, 0x04, 0x05, 0x06, 0x30
NO_SUCH_OBJECT, END_OF_MIB_VIEW = 0x80, 0x82  # v2c exception values
GET, GETNEXT, RESPONSE = 0xA0, 0xA1, 0xA2
NO_SUCH_NAME = 2  # v1 error-status
VERSIONS = (0, 1)  # v1, v2c

type Oid = tuple[int, ...]
type VarBind = tuple[Oid, int, bytes]  # (name, value tag, value content)
type Status = tuple[int, int, bytes]  # hrDeviceStatus, hrPrinterStatus, hrPrinterDetectedErrorState

SYS_DESCR: Oid = (1, 3, 6, 1, 2, 1, 1, 1, 0)
HR_DEVICE_STATUS: Oid = (1, 3, 6, 1, 2, 1, 25, 3, 2, 1, 5)
HR_PRINTER_STATUS: Oid = (1, 3, 6, 1, 2, 1, 25, 3, 5, 1, 1)
HR_PRINTER_DETECTED_ERROR_STATE: Oid = (1, 3, 6, 1, 2, 1, 25, 3, 5, 1, 2)
_STATUS_COLUMNS = (HR_DEVICE_STATUS, HR_PRINTER_STATUS, HR_PRINTER_DETECTED_ERROR_STATE)

# hrPrinterDetectedErrorState bits (RFC 3805); bit 0 is the most significant bit of the octet.
_ERROR_BITS = {
    PrinterFault.PAPER_NEAR_END: 0x80,  # lowPaper
    PrinterFault.PAPER_OUT: 0x40,  # noPaper
    PrinterFault.COVER_OPEN: 0x08,  # doorOpen
    PrinterFault.OFFLINE: 0x02,  # offline
}


def printer_status(faults: Collection[str]) -> Status:
    """The status objects for a printer's active faults (RFC 3805 2.2.13.2, checked on Windows)."""
    error_state = bytes([sum(bit for fault, bit in _ERROR_BITS.items() if fault in faults)])
    if any(fault in faults for fault in BLOCKING_FAULTS):
        return 5, 1, error_state  # down, other: the queue shows the error and holds jobs
    if PrinterFault.PAPER_NEAR_END in faults:
        return 3, 3, error_state  # warning, idle: Windows shows nothing and keeps printing
    return 2, 3, error_state  # running, idle


@dataclass(frozen=True, slots=True)
class Message:
    version: int
    community: bytes
    pdu_type: int
    request_id: int
    varbinds: tuple[VarBind, ...]
    error_status: int = 0
    error_index: int = 0


@dataclass(frozen=True, slots=True)
class Answer:
    reply: bytes
    type: Literal["get", "getnext"]
    oids: tuple[str, ...]  # the requested object identifiers, dotted
    indexes: frozenset[int]  # SNMP indexes whose status objects the reply carries


def answer(packet: bytes, statuses: Mapping[int, Status]) -> Answer | None:
    """The reply to a v1/v2c GET or GETNEXT, given each SNMP index's status; None to stay silent.

    Malformed packets, other versions and other PDU types (such as SET) get no reply.
    """
    try:
        request = decode_message(packet)
    except (ValueError, IndexError):
        return None
    if request.version not in VERSIONS or request.pdu_type not in (GET, GETNEXT):
        return None
    mib = _mib(statuses)
    varbinds: list[VarBind] = []
    error_status = error_index = 0
    for position, (oid, _, _) in enumerate(request.varbinds, start=1):
        if request.pdu_type == GET:
            found, missing = (oid if oid in mib else None), NO_SUCH_OBJECT
        else:
            found, missing = next((o for o in sorted(mib) if o > oid), None), END_OF_MIB_VIEW
        if found is not None:
            varbinds.append((found, *mib[found]))
        elif request.version == 0:  # v1 has no exception values: the whole request fails
            varbinds, error_status, error_index = list(request.varbinds), NO_SUCH_NAME, position
            break
        else:
            varbinds.append((oid, missing, b""))
    reply = Message(
        request.version,
        request.community,
        RESPONSE,
        request.request_id,
        tuple(varbinds),
        error_status,
        error_index,
    )
    return Answer(
        encode_message(reply),
        "get" if request.pdu_type == GET else "getnext",
        tuple(".".join(map(str, oid)) for oid, _, _ in request.varbinds),
        frozenset(
            oid[-1]
            for oid, _, _ in varbinds
            if error_status == 0 and oid[:-1] in _STATUS_COLUMNS and oid in mib
        ),
    )


def _mib(statuses: Mapping[int, Status]) -> dict[Oid, tuple[int, bytes]]:
    mib = {SYS_DESCR: (OCTET_STRING, b"emupos")}
    for index, (device_status, printer_status_value, error_state) in statuses.items():
        mib[(*HR_DEVICE_STATUS, index)] = (INTEGER, _int_content(device_status))
        mib[(*HR_PRINTER_STATUS, index)] = (INTEGER, _int_content(printer_status_value))
        mib[(*HR_PRINTER_DETECTED_ERROR_STATE, index)] = (OCTET_STRING, error_state)
    return mib


# --- BER -------------------------------------------------------------------------------------


def encode_message(message: Message) -> bytes:
    varbind_list = b"".join(
        _tlv(SEQUENCE, _tlv(OBJECT_ID, _oid_content(oid)) + _tlv(tag, value))
        for oid, tag, value in message.varbinds
    )
    pdu = b"".join(
        _tlv(INTEGER, _int_content(value))
        for value in (message.request_id, message.error_status, message.error_index)
    )
    return _tlv(
        SEQUENCE,
        _tlv(INTEGER, _int_content(message.version))
        + _tlv(OCTET_STRING, message.community)
        + _tlv(message.pdu_type, pdu + _tlv(SEQUENCE, varbind_list)),
    )


def decode_message(packet: bytes) -> Message:
    """Decode a v1/v2c message. Raises ValueError or IndexError when it is not one."""
    tag, body, end = _read_tlv(packet, 0)
    if tag != SEQUENCE or end != len(packet):
        raise ValueError("not a single BER SEQUENCE")
    (version_tag, version), (community_tag, community), (pdu_type, pdu) = _children(body)
    if version_tag != INTEGER or community_tag != OCTET_STRING:
        raise ValueError("not an SNMP v1/v2c message")
    (_, request_id), (_, error_status), (_, error_index), (list_tag, varbind_list) = _children(pdu)
    if list_tag != SEQUENCE:
        raise ValueError("no variable bindings")
    varbinds: list[VarBind] = []
    for _, varbind in _children(varbind_list):
        (oid_tag, oid), (value_tag, value) = _children(varbind)
        if oid_tag != OBJECT_ID:
            raise ValueError("a variable binding name is not an OID")
        varbinds.append((_decode_oid(oid), value_tag, value))
    return Message(
        _decode_int(version),
        community,
        pdu_type,
        _decode_int(request_id),
        tuple(varbinds),
        _decode_int(error_status),
        _decode_int(error_index),
    )


def _tlv(tag: int, content: bytes) -> bytes:
    length = len(content)
    if length < 0x80:
        return bytes([tag, length]) + content
    size = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(size)]) + size + content


def _read_tlv(data: bytes, pos: int) -> tuple[int, bytes, int]:
    """(tag, content, position after the element)."""
    tag, first = data[pos], data[pos + 1]
    pos += 2
    if first >= 0x80:
        size = first & 0x7F
        if not 1 <= size <= 4 or pos + size > len(data):
            raise ValueError("unsupported length")
        length = int.from_bytes(data[pos : pos + size], "big")
        pos += size
    else:
        length = first
    if pos + length > len(data):
        raise ValueError("truncated element")
    return tag, data[pos : pos + length], pos + length


def _children(content: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    pos = 0
    while pos < len(content):
        tag, value, pos = _read_tlv(content, pos)
        items.append((tag, value))
    return items


def _int_content(value: int) -> bytes:
    """Minimal two's-complement bytes."""
    bits = value.bit_length() if value >= 0 else (~value).bit_length()
    return value.to_bytes(bits // 8 + 1, "big", signed=True)


def _decode_int(content: bytes) -> int:
    if not content:
        raise ValueError("empty INTEGER")
    return int.from_bytes(content, "big", signed=True)


def _oid_content(oid: Oid) -> bytes:
    body = bytearray()
    for sub_id in (40 * oid[0] + oid[1], *oid[2:]):  # the first two arcs share one sub-id
        chunk = [sub_id & 0x7F]
        while sub_id := sub_id >> 7:  # base 128, high bit set on every byte but the last
            chunk.append(0x80 | (sub_id & 0x7F))
        body.extend(reversed(chunk))
    return bytes(body)


def _decode_oid(content: bytes) -> Oid:
    sub_ids: list[int] = []
    value = 0
    for byte in content:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            sub_ids.append(value)
            value = 0
    first = sub_ids[0]
    return (min(first // 40, 2), first - 40 * min(first // 40, 2), *sub_ids[1:])
