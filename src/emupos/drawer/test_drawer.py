"""Scenarios of the cash-drawer spec, played through the printer the drawer is attached to."""

from emupos.drawer.drawer import Drawer, Pulse, dle_dc4_pulse, esc_p_pulse
from emupos.events import EventType
from emupos.printer.test_support import Pos

KICK_PIN_2 = "1b 70 00 19 fa"

# --- One drawer attached to each printer ------------------------------------------------------


def test_drawer_starts_closed() -> None:
    assert Pos().printer.state().drawer == "closed"


def test_kick_on_one_connection_is_visible_on_another() -> None:
    serial, tcp = "serial:/tmp/emupos/front", "tcp:127.0.0.1:9100<-127.0.0.1:53422"
    pos = Pos(connections=(serial, tcp))

    pos.send(KICK_PIN_2, serial)
    pos.send("10 04 01", tcp)

    assert pos.take(tcp) == bytes.fromhex("16")


# --- ESC p drawer kick ------------------------------------------------------------------------


def test_pulse_on_pin_2() -> None:
    pos = Pos()

    pos.send(KICK_PIN_2)

    assert pos.printer.state().drawer == "open"
    [opened] = pos.events_of(EventType.DRAWER_OPENED)
    assert opened.device_id == "front"
    assert opened.data == {"pin": 2, "on_time_ms": 50}


def test_pulse_on_pin_5_with_an_ascii_pin_parameter() -> None:
    pos = Pos()

    pos.send("1b 70 31 32 64")

    assert pos.printer.state().drawer == "open"
    [opened] = pos.events_of(EventType.DRAWER_OPENED)
    assert opened.data == {"pin": 5, "on_time_ms": 100}


def test_kick_while_already_open() -> None:
    pos = Pos()
    pos.send(KICK_PIN_2)

    pos.send(KICK_PIN_2)

    assert pos.printer.state().drawer == "open"
    assert len(pos.events_of(EventType.DRAWER_OPENED)) == 1


def test_kick_held_behind_paper_out() -> None:
    pos = Pos()
    pos.set_fault("paper-out")

    pos.send(KICK_PIN_2)
    while_active = pos.printer.state().drawer
    pos.set_fault("paper-out", active=False)

    assert while_active == "closed"
    assert pos.printer.state().drawer == "open"
    assert len(pos.events_of(EventType.DRAWER_OPENED)) == 1


def test_kick_on_an_invalid_pin_is_reported() -> None:
    pos = Pos()

    pos.send("1b 70 02 19 fa")

    assert pos.printer.state().drawer == "closed"
    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert unknown.data["bytes"] == "1b 70 02 19 fa"


# --- Real-time drawer pulse -------------------------------------------------------------------


def test_real_time_pulse_opens_the_drawer_while_printing_is_blocked() -> None:
    pos = Pos()
    pos.set_fault("cover-open")

    pos.send("10 14 01 00 01")

    assert pos.printer.state().drawer == "open"
    [opened] = pos.events_of(EventType.DRAWER_OPENED)
    assert opened.data == {"pin": 2, "on_time_ms": 100}


def test_real_time_pulse_out_of_range_is_reported() -> None:
    pos = Pos()

    pos.send("10 14 01 00 09")

    assert pos.printer.state().drawer == "closed"
    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert unknown.data["bytes"] == "10 14 01 00 09"


# --- Drawer stays open until closed by the user -----------------------------------------------


def test_drawer_left_open() -> None:
    pos = Pos()
    pos.send(KICK_PIN_2)

    pos.wait(600)

    assert pos.printer.state().drawer == "open"


def test_closing_through_the_api() -> None:
    pos = Pos()
    pos.send(KICK_PIN_2)

    pos.close_drawer()
    pos.close_drawer()

    assert pos.printer.state().drawer == "closed"
    [closed] = pos.events_of(EventType.DRAWER_CLOSED)
    assert closed.device_id == "front"


# --- Drawer sensor level ----------------------------------------------------------------------


def test_sensor_high_when_open() -> None:
    pos = Pos(sensor_open_level="high")

    pos.send("10 04 01")
    pos.send(KICK_PIN_2)
    pos.send("10 04 01")

    assert pos.take() == bytes.fromhex("12 16")


def test_sensor_low_when_open() -> None:
    pos = Pos(sensor_open_level="low")

    pos.send("10 04 01")
    pos.send(KICK_PIN_2)
    pos.send("10 04 01")

    assert pos.take() == bytes.fromhex("16 12")


def test_drawer_level_reported_while_the_printer_is_offline() -> None:
    pos = Pos(sensor_open_level="high")
    pos.send(KICK_PIN_2)
    pos.set_fault("cover-open")

    pos.send("10 04 01")

    assert pos.take() == bytes.fromhex("1e")


# --- Drawer state in GS r and Automatic Status Back -------------------------------------------


def test_gs_r_reports_the_drawer() -> None:
    pos = Pos(sensor_open_level="high")

    pos.send("1d 72 02")
    pos.send(KICK_PIN_2)
    pos.send("1d 72 32")

    assert pos.take() == bytes.fromhex("00 01")  # pin 3 low, then high


def test_asb_pushes_drawer_changes() -> None:
    pos = Pos(connections=("A", "B"))
    pos.send("1d 61 ff", "A")
    initial = pos.take("A")

    pos.send(KICK_PIN_2, "B")
    on_open = pos.take("A")
    pos.close_drawer()
    on_close = pos.take("A")

    assert on_open == bytes.fromhex("14 00 00 00")
    assert on_close == initial == bytes.fromhex("10 00 00 00")


# --- Pulse decoding ---------------------------------------------------------------------------


def test_pulse_parameters() -> None:
    assert esc_p_pulse(48, 50) == Pulse(2, 100)
    assert esc_p_pulse(49, 1) == Pulse(5, 2)
    assert esc_p_pulse(2, 50) is None
    assert dle_dc4_pulse(1, 8) == Pulse(5, 800)
    assert dle_dc4_pulse(0, 0) is None
    assert dle_dc4_pulse(48, 1) is None


def test_drawer_alone() -> None:
    drawer = Drawer("front", "low")

    assert drawer.pin3_high  # closed, with a sensor that is low when open
    assert drawer.close() is None
    assert drawer.kick(Pulse(2, 50)) is not None
    assert not drawer.pin3_high
