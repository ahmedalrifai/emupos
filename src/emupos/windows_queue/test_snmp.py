import pytest

from emupos.windows_queue import snmp
from emupos.windows_queue.snmp import (
    GET,
    GETNEXT,
    HR_DEVICE_STATUS,
    HR_PRINTER_DETECTED_ERROR_STATE,
    HR_PRINTER_STATUS,
    NULL,
    SYS_DESCR,
    Message,
    Oid,
    decode_message,
    encode_message,
    printer_status,
)

READY = printer_status(())


def request(
    oids: list[Oid], *, version: int = 0, pdu_type: int = GET, community: bytes = b"public"
) -> bytes:
    varbinds = tuple((oid, NULL, b"") for oid in oids)
    return encode_message(Message(version, community, pdu_type, 4242, varbinds))


def status_oids(index: int) -> list[Oid]:
    columns = (HR_DEVICE_STATUS, HR_PRINTER_STATUS, HR_PRINTER_DETECTED_ERROR_STATE)
    return [(*column, index) for column in columns]


def reply(packet: bytes, statuses: dict[int, snmp.Status]) -> Message:
    answer = snmp.answer(packet, statuses)
    assert answer is not None
    message = decode_message(answer.reply)
    assert (message.pdu_type, message.request_id) == (snmp.RESPONSE, 4242)
    return message


def test_ber_matches_hand_checked_bytes() -> None:
    # a v1 GET of sysDescr.0, the request the Windows port monitor sends (spike 1.3)
    packet = request([SYS_DESCR], community=b"public")

    assert packet.hex(" ") == (
        "30 27 02 01 00 04 06 70 75 62 6c 69 63 a0 1a 02 02 10 92 02 01 00 02 01 00 "
        "30 0e 30 0c 06 08 2b 06 01 02 01 01 01 00 05 00"
    )
    assert decode_message(packet).varbinds == ((SYS_DESCR, NULL, b""),)


def test_large_values_round_trip() -> None:
    oid = (1, 3, 6, 1, 4, 1, 32473, 9100)
    message = Message(1, b"x" * 300, GET, -129, ((oid, snmp.OCTET_STRING, bytes(300)),))

    assert decode_message(encode_message(message)) == message


@pytest.mark.parametrize(
    ("faults", "expected"),
    [
        ((), (2, 3, b"\x00")),
        (("paper-near-end",), (3, 3, b"\x80")),
        (("paper-out",), (5, 1, b"\x40")),
        (("cover-open",), (5, 1, b"\x08")),
        (("offline",), (5, 1, b"\x02")),
        (("cover-open", "paper-near-end"), (5, 1, b"\x88")),
    ],
)
def test_printer_status(faults: tuple[str, ...], expected: snmp.Status) -> None:
    assert printer_status(faults) == expected


@pytest.mark.parametrize("version", [0, 1])
def test_status_get_for_one_index(version: int) -> None:
    statuses = {9100: printer_status(("paper-out",)), 9101: READY}

    answer = snmp.answer(request(status_oids(9100), version=version), statuses)

    assert answer is not None
    assert answer.type == "get"
    assert answer.oids[0] == "1.3.6.1.2.1.25.3.2.1.5.9100"
    assert answer.indexes == {9100}
    values = [value for _, _, value in decode_message(answer.reply).varbinds]
    assert values == [b"\x05", b"\x01", b"\x40"]


def test_discovery_requests_name_no_printer() -> None:
    discovery = snmp.answer(request([SYS_DESCR]), {9100: READY})
    walk = snmp.answer(request([(1, 3, 6, 1, 4, 1, 2699, 1, 2)], pdu_type=GETNEXT), {9100: READY})

    assert discovery is not None
    assert discovery.indexes == frozenset()
    assert decode_message(discovery.reply).varbinds == ((SYS_DESCR, snmp.OCTET_STRING, b"emupos"),)
    assert walk is not None
    assert (walk.type, walk.indexes) == ("getnext", frozenset())
    assert decode_message(walk.reply).error_status == snmp.NO_SUCH_NAME  # past the last object


def test_getnext_walk_visits_every_object_in_order() -> None:
    statuses = {2: READY, 1: READY}
    oid: Oid = (1, 3, 6, 1)
    walked: list[Oid] = []
    while True:
        ((found, tag, _),) = reply(request([oid], version=1, pdu_type=GETNEXT), statuses).varbinds
        if tag == snmp.END_OF_MIB_VIEW:
            break
        walked.append(found)
        oid = found

    assert walked == [SYS_DESCR, *sorted(status_oids(1) + status_oids(2))]


def test_unknown_index() -> None:
    v2c = reply(request(status_oids(9101)[:1], version=1), {9100: READY})
    v1 = snmp.answer(request([SYS_DESCR, *status_oids(9101)]), {9100: READY})

    assert v2c.varbinds[0][1] == snmp.NO_SUCH_OBJECT
    assert v1 is not None
    assert v1.indexes == frozenset()
    assert (decode_message(v1.reply).error_status, decode_message(v1.reply).error_index) == (2, 2)


@pytest.mark.parametrize(
    "packet",
    [
        b"garbage",
        b"",
        b"\x30\x05\x02\x01",
        request([SYS_DESCR], pdu_type=0xA3),  # SET
        request([SYS_DESCR], pdu_type=0xA5, version=1),  # GETBULK
        request([SYS_DESCR], version=3),
        bytes.fromhex("30 0e 02 01 01 04 06 70 75 62 6c 69 63 a0 00"),
    ],
)
def test_silent_for_anything_else(packet: bytes) -> None:
    assert snmp.answer(packet, {9100: READY}) is None
