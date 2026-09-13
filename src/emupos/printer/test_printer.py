"""Scenarios of the receipt-printer spec, played against `Printer` (rendering: escpos/test_render.py)."""

import random

from hypothesis import given, settings
from hypothesis import strategies as st

from emupos.events import EventType
from emupos.printer.test_support import Pos, image_of

HI_CUT = "48 69 0a 1d 56 00"

# --- Incremental ESC/POS decoding -----------------------------------------------------------


def test_command_split_across_reads() -> None:
    pos = Pos()

    pos.send("48 69 0a 1d")
    pos.send("56 00")

    assert pos.texts == ["Hi\n"]
    assert pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN) == []


def test_unknown_command_is_skipped() -> None:
    pos = Pos()

    pos.send("1b 40 1b fe 48 69 0a 1d 56 00")

    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert "1b fe" in str(unknown.data["bytes"])
    assert pos.texts == ["Hi\n"]


def test_truncated_command_at_connection_close() -> None:
    pos = Pos()

    pos.send("48 69 0a 1d 76 30 00")
    pos.close()

    assert pos.texts == ["Hi\n"]
    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert "1d 76 30 00" in str(unknown.data["bytes"])


def test_random_bytes_do_not_stop_the_printer() -> None:
    pos = Pos()

    pos.send(random.Random(1).randbytes(10000))  # noqa: S311 (test data, not security)
    pos.close()
    pos.connect("B")
    pos.take("A")
    pos.send("10 04 01", "B")

    assert len(pos.take("B")) == 1


@settings(max_examples=60, deadline=None)
@given(st.binary(max_size=3000), st.sampled_from(["paper-out", "paper-near-end", None]))
def test_any_bytes_never_raise(data: bytes, fault: str | None) -> None:
    pos = Pos()
    if fault:
        pos.set_fault(fault)
    pos.send(data)
    pos.wait(3)
    pos.close()
    if fault:
        pos.set_fault(fault, active=False)


# --- Real-time commands -----------------------------------------------------------------------


def test_status_query_inside_a_line_of_text() -> None:
    pos = Pos()

    pos.send("48 65 10 04 01 6c 6c 6f 0a 1d 56 00")

    assert len(pos.take()) == 1
    assert pos.texts == ["Hello\n"]


def test_status_query_answered_while_printing_is_blocked() -> None:
    pos = Pos()
    pos.set_fault("paper-out")
    pos.send(HI_CUT)

    pos.send("10 04 04")

    assert len(pos.take()) == 1
    assert pos.receipts == []


def test_real_time_command_without_an_effect_is_reported() -> None:
    pos = Pos()

    pos.send("10 05 01 41 0a 1d 56 00")  # DLE ENQ

    assert pos.take() == b""
    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert unknown.data["bytes"] == "10 05 01"
    assert pos.texts == ["A\n"]


# --- DLE EOT status replies -------------------------------------------------------------------


def test_printer_with_no_faults() -> None:
    pos = Pos()

    pos.send("10 04 01 10 04 02 10 04 03 10 04 04")

    assert pos.take() == bytes.fromhex("12 12 12 12")


def test_cover_open() -> None:
    pos = Pos()
    pos.set_fault("cover-open")

    pos.send("10 04 01 10 04 02")

    assert pos.take() == bytes.fromhex("1a 16")


def test_paper_out() -> None:
    pos = Pos()
    pos.set_fault("paper-out")

    pos.send("10 04 01 10 04 02 10 04 04")

    assert pos.take() == bytes.fromhex("1a 32 7e")


def test_out_of_range_request() -> None:
    pos = Pos()

    pos.send("10 04 05 10 04 01")

    assert pos.take() == bytes.fromhex("12")
    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert "10 04 05" in str(unknown.data["bytes"])


# --- Automatic Status Back --------------------------------------------------------------------


def test_enabling_asb_sends_the_current_status() -> None:
    pos = Pos()

    pos.send("1d 61 ff")

    assert len(pos.take()) == 4


def test_fault_changes_push_a_new_status() -> None:
    pos = Pos()
    pos.send("1d 61 ff")
    initial = pos.take()

    pos.set_fault("paper-out")
    on_activation = pos.take()
    pos.set_fault("paper-out", active=False)
    on_clearing = pos.take()

    assert len(on_activation) == 4
    assert on_activation != initial
    assert on_clearing == initial


def test_disabling_asb() -> None:
    pos = Pos()
    pos.send("1d 61 ff")
    pos.take()

    pos.send("1d 61 00")
    pos.set_fault("cover-open")

    assert pos.take() == b""


def test_asb_is_per_connection() -> None:
    pos = Pos(connections=("A", "B"))
    pos.send("1d 61 ff", "A")
    pos.take("A")

    pos.set_fault("offline")

    assert len(pos.take("A")) == 4
    assert pos.take("B") == b""


def test_asb_ends_when_the_connection_closes() -> None:
    pos = Pos(connections=("A", "B"))
    pos.send("1d 61 ff", "A")
    pos.close("A")
    pos.take("A")

    pos.connect("A")
    pos.set_fault("cover-open")

    assert pos.take("A") == b""


# --- GS r transmit status ---------------------------------------------------------------------


def test_paper_sensor_status_follows_paper_state() -> None:
    pos = Pos()

    pos.send("1d 72 01")
    first = pos.take()
    pos.set_fault("paper-near-end")
    pos.send("1d 72 31")
    second = pos.take()

    assert first == bytes.fromhex("00")  # paper present, not near end
    assert second == bytes.fromhex("03")  # near end


def test_gs_r_waits_behind_a_blocking_fault() -> None:
    pos = Pos()
    pos.set_fault("cover-open")

    pos.send("1d 72 01")
    while_blocked = pos.take()
    pos.set_fault("cover-open", active=False)

    assert while_blocked == b""
    assert len(pos.take()) == 1


# --- Supported print commands -----------------------------------------------------------------


def test_pdf417_is_consumed_without_breaking_following_commands() -> None:
    pos = Pos()

    pos.send("1d 28 6b 03 00 30 41 00 4f 4b 0a 1d 56 00")

    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert "1d 28 6b 03 00 30 41 00" in str(unknown.data["bytes"])
    assert pos.texts == ["OK\n"]


def test_page_mode_is_not_entered() -> None:
    pos = Pos()

    pos.send("1b 4c 48 69 0a 1d 56 00")

    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert unknown.data["bytes"] == "1b 4c"
    assert pos.texts == ["Hi\n"]
    assert pos.receipts[0].height_dots == 24  # one standard-mode line of Font A


def test_nv_graphics_are_consumed_in_full() -> None:
    pos = Pos()

    pos.send("1d 28 4c 06 00 30 45 20 20 01 01 4f 4b 0a 1d 56 00")

    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert unknown.data["bytes"] == "1d 28 4c 06 00 30 45 20 20 01 01"
    assert pos.texts == ["OK\n"]


def test_nv_graphics_capacity_is_reported_as_zero() -> None:
    pos = Pos()

    pos.send("1d 28 4c 02 00 30 30 1d 28 4c 02 00 30 33")

    assert pos.take() == bytes.fromhex("37 30 30 00 37 31 30 00")  # "0" bytes, then "0" free
    assert pos.events == []


# --- Job boundaries ---------------------------------------------------------------------------


def test_cuts_separate_receipts_on_one_connection() -> None:
    pos = Pos()

    pos.send("41 0a 1d 56 00 42 0a 1d 56 00")

    assert pos.texts == ["A\n", "B\n"]
    assert [r.boundary for r in pos.receipts] == ["cut", "cut"]


def test_connection_close_ends_the_job() -> None:
    pos = Pos()

    pos.send("1b 40 48 69 0a")
    pos.close()

    assert pos.texts == ["Hi\n"]
    assert pos.receipts[0].boundary == "connection-closed"


def test_idle_timeout_ends_the_job() -> None:
    pos = Pos(job_idle_timeout_ms=2000)
    pos.wait(5)

    pos.send("1b 40 48 69 0a")
    deadline = pos.printer.next_deadline()
    pos.wait(1.999)
    before = list(pos.receipts)
    pos.wait(0.001)

    assert deadline == 7.0
    assert before == []
    assert pos.texts == ["Hi\n"]
    assert pos.receipts[0].boundary == "idle-timeout"
    assert pos.printer.next_deadline() is None


def test_each_byte_restarts_the_idle_timeout() -> None:
    pos = Pos(job_idle_timeout_ms=2000)

    pos.send("48 69")
    pos.wait(1.5)
    pos.send("0a")
    pos.wait(1.5)

    assert pos.receipts == []


def test_status_polling_produces_no_receipt() -> None:
    pos = Pos()

    pos.send("1b 40 10 04 01 1b 70 00 19 fa")
    pos.take()
    pos.close()
    pos.wait(10)

    assert pos.receipts == []


# --- Receipt output ---------------------------------------------------------------------------


def test_completed_job_is_rendered_576_dots_wide() -> None:
    pos = Pos()

    pos.send("1b 40 48 69 0a 1d 56 00")

    [receipt] = pos.receipts
    assert image_of(receipt).size == (576, receipt.height_dots)
    assert receipt.width_dots == 576
    assert receipt.text == "Hi\n"


def test_text_dump_marks_a_barcode() -> None:
    pos = Pos()

    pos.send(
        b"TOTAL\n" + bytes.fromhex("1d 6b 43 0d") + b"4006381333931" + bytes.fromhex("1d 56 00")
    )

    assert pos.texts == ["TOTAL\n[barcode EAN-13 4006381333931]\n"]


# --- Printer faults ---------------------------------------------------------------------------


def test_faults_start_inactive() -> None:
    assert Pos().printer.state().faults == ()


def test_paper_out_holds_a_receipt_until_cleared() -> None:
    pos = Pos()
    pos.set_fault("paper-out")

    pos.send("1b 40 48 69 0a 1d 56 00")
    pos.close()
    pos.wait(10)
    while_active = list(pos.receipts)
    pos.set_fault("paper-out", active=False)

    assert while_active == []
    assert pos.texts == ["Hi\n"]


def test_job_of_a_connection_closed_while_held_completes_on_clearing() -> None:
    pos = Pos()
    pos.set_fault("offline")

    pos.send("48 69 0a")
    pos.close()
    pos.set_fault("offline", active=False)

    assert pos.texts == ["Hi\n"]
    assert pos.receipts[0].boundary == "connection-closed"


def test_offline_printer_holds_data() -> None:
    pos = Pos()
    pos.set_fault("offline")

    pos.send("48 69 0a 1d 56 00 10 04 01")

    assert pos.take() == bytes.fromhex("1a")
    assert pos.receipts == []


def test_paper_near_end_still_prints() -> None:
    pos = Pos()
    pos.set_fault("paper-near-end")

    pos.send("48 69 0a 1d 56 00 10 04 01 10 04 04")

    assert pos.texts == ["Hi\n"]
    assert pos.take() == bytes.fromhex("12 1e")


def test_status_change_events() -> None:
    pos = Pos()

    pos.set_fault("cover-open")
    pos.set_fault("cover-open")

    [changed] = pos.events_of(EventType.PRINTER_STATUS_CHANGED)
    assert changed.device_id == "front"
    assert changed.data["faults"] == ["cover-open"]


def test_clearing_an_inactive_fault_emits_nothing() -> None:
    pos = Pos()

    pos.set_fault("offline", active=False)

    assert pos.events == []


def test_data_is_held_until_the_last_blocking_fault_clears() -> None:
    pos = Pos()
    pos.set_fault("paper-out")
    pos.set_fault("cover-open")
    pos.send("41 0a 1d 56 00 1b 70 00 19 fa 42 0a 1d 56 00")

    pos.set_fault("paper-out", active=False)
    after_first = list(pos.receipts)
    pos.set_fault("cover-open", active=False)

    assert after_first == []
    assert pos.texts == ["A\n", "B\n"]
    assert pos.printer.state().drawer == "open"
    assert pos.events_of(EventType.PRINTER_STATUS_CHANGED)[-1].data["faults"] == []


def test_idle_timeout_does_not_complete_a_held_job() -> None:
    pos = Pos()
    pos.send("48 69 0a")
    pos.set_fault("cover-open")

    pos.wait(10)

    assert pos.receipts == []
    assert pos.printer.next_deadline() is None


# --- Multiple simultaneous connections --------------------------------------------------------


def test_interleaved_jobs_stay_separate() -> None:
    pos = Pos(connections=("A", "B"))

    pos.send("41 41 0a", "A")
    pos.send("42 42 0a", "B")
    pos.send("1d 56 00", "A")
    pos.send("1d 56 00", "B")

    assert pos.texts == ["AA\n", "BB\n"]


def test_tcp_and_serial_share_printer_state() -> None:
    tcp, serial = "tcp:127.0.0.1:9100<-127.0.0.1:53422", "serial:/tmp/emupos/front"
    pos = Pos(connections=(tcp, serial))

    pos.set_fault("paper-out")
    pos.send("10 04 04", tcp)
    pos.send("10 04 04", serial)

    assert pos.take(tcp) == bytes.fromhex("7e")
    assert pos.take(serial) == bytes.fromhex("7e")


def test_replies_return_to_the_requesting_connection() -> None:
    pos = Pos(connections=("A", "B"))

    pos.send("10 04 01", "A")

    assert len(pos.take("A")) == 1
    assert pos.take("B") == b""


def test_new_connection_starts_with_initial_settings() -> None:
    pos = Pos(connections=("A", "B"))

    pos.send("1d 21 11 1b 61 01", "A")  # double size, centred
    pos.send("41 0a 1d 56 00", "B")

    [receipt] = pos.receipts
    assert receipt.height_dots == 24
