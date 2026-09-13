"""Status bytes a printer sends: DLE EOT, GS r and Automatic Status Back (GS a).

Every reply is computed from one `StatusState` snapshot (design D6), with the bit layouts of
the Epson ESC/POS Command Reference for TM printers:
- DLE EOT: https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/dle_eot.html
- GS r:    https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lr.html
- GS a:    https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_la.html
Bits the simulator never sets (paper feed button, cutter and unrecoverable errors, ...) are
listed so the tables read like the manual.
"""

from dataclasses import dataclass
from enum import IntFlag


@dataclass(frozen=True, slots=True)
class StatusState:
    paper_near_end: bool = False
    paper_out: bool = False
    cover_open: bool = False
    offline: bool = False
    drawer_pin3_high: bool = False

    @property
    def is_offline(self) -> bool:
        """The printer reports offline while any fault stops printing."""
        return self.offline or self.cover_open or self.paper_out


# --- DLE EOT n: one byte, 0xx1xx10 --------------------------------------------------------


class PrinterStatus(IntFlag):  # n = 1
    FIXED = 0x12
    DRAWER_KICK_OUT_CONNECTOR_PIN_3_HIGH = 0x04
    OFFLINE = 0x08
    WAITING_FOR_ONLINE_RECOVERY = 0x20
    PAPER_FEED_BUTTON_PRESSED = 0x40


class OfflineCauseStatus(IntFlag):  # n = 2
    FIXED = 0x12
    COVER_OPEN = 0x04
    PAPER_BEING_FED_BY_BUTTON = 0x08
    PRINTING_STOPPED_BY_PAPER_END = 0x20
    ERROR_OCCURRED = 0x40


class ErrorCauseStatus(IntFlag):  # n = 3
    FIXED = 0x12
    RECOVERABLE_ERROR = 0x04
    AUTOCUTTER_ERROR = 0x08
    UNRECOVERABLE_ERROR = 0x20
    AUTO_RECOVERABLE_ERROR = 0x40


class RollPaperSensorStatus(IntFlag):  # n = 4
    FIXED = 0x12
    NEAR_END = 0x0C  # bits 2 and 3
    PAPER_NOT_PRESENT = 0x60  # bits 5 and 6


def dle_eot(n: int, state: StatusState) -> bytes | None:
    """The reply to DLE EOT n, or None when n requests no status the simulator provides."""
    match n:
        case 1:
            status = PrinterStatus.FIXED
            if state.drawer_pin3_high:
                status |= PrinterStatus.DRAWER_KICK_OUT_CONNECTOR_PIN_3_HIGH
            if state.is_offline:
                status |= PrinterStatus.OFFLINE
        case 2:
            status = OfflineCauseStatus.FIXED
            if state.cover_open:
                status |= OfflineCauseStatus.COVER_OPEN
            if state.paper_out:
                status |= OfflineCauseStatus.PRINTING_STOPPED_BY_PAPER_END
        case 3:
            status = ErrorCauseStatus.FIXED
        case 4:
            status = RollPaperSensorStatus.FIXED
            if state.paper_near_end or state.paper_out:
                status |= RollPaperSensorStatus.NEAR_END
            if state.paper_out:
                status |= RollPaperSensorStatus.PAPER_NOT_PRESENT
        case _:
            return None
    return bytes([status])


# --- GS r n: one byte ---------------------------------------------------------------------


class PaperSensorStatus(IntFlag):  # n = 1, 49
    NEAR_END = 0x03  # bits 0 and 1
    PAPER_NOT_PRESENT = 0x0C  # bits 2 and 3


class DrawerKickOutConnectorStatus(IntFlag):  # n = 2, 50
    PIN_3_HIGH = 0x01


def gs_r(n: int, state: StatusState) -> bytes | None:
    """The reply to GS r n, or None for n values without a simulated status (e.g. ink)."""
    match n:
        case 1 | 49:
            status = PaperSensorStatus(0)
            if state.paper_near_end or state.paper_out:
                status |= PaperSensorStatus.NEAR_END
            if state.paper_out:
                status |= PaperSensorStatus.PAPER_NOT_PRESENT
        case 2 | 50:
            status = DrawerKickOutConnectorStatus(0)
            if state.drawer_pin3_high:
                status |= DrawerKickOutConnectorStatus.PIN_3_HIGH
        case _:
            return None
    return bytes([status])


# --- Automatic Status Back: four bytes ----------------------------------------------------


class AsbFirstByte(IntFlag):
    FIXED = 0x10
    DRAWER_KICK_OUT_CONNECTOR_PIN_3_HIGH = 0x04
    OFFLINE = 0x08
    COVER_OPEN = 0x20
    PAPER_BEING_FED_BY_BUTTON = 0x40


class AsbSecondByte(IntFlag):
    WAITING_FOR_ONLINE_RECOVERY = 0x01
    PAPER_FEED_BUTTON_PUSHED = 0x02
    RECOVERABLE_ERROR = 0x04
    AUTOCUTTER_ERROR = 0x08
    UNRECOVERABLE_ERROR = 0x20
    AUTO_RECOVERABLE_ERROR = 0x40


class AsbThirdByte(IntFlag):
    NEAR_END = 0x03  # bits 0 and 1
    PAPER_NOT_PRESENT = 0x0C  # bits 2 and 3


class AsbEnabled(IntFlag):
    """The bits of n in GS a n: which status categories trigger a new ASB status."""

    DRAWER = 0x01
    ONLINE_OFFLINE = 0x02
    ERROR = 0x04
    ROLL_PAPER_SENSOR = 0x08
    PANEL_SWITCH = 0x40


def asb(state: StatusState) -> bytes:
    first = AsbFirstByte.FIXED
    if state.drawer_pin3_high:
        first |= AsbFirstByte.DRAWER_KICK_OUT_CONNECTOR_PIN_3_HIGH
    if state.is_offline:
        first |= AsbFirstByte.OFFLINE
    if state.cover_open:
        first |= AsbFirstByte.COVER_OPEN
    third = AsbThirdByte(0)
    if state.paper_near_end or state.paper_out:
        third |= AsbThirdByte.NEAR_END
    if state.paper_out:
        third |= AsbThirdByte.PAPER_NOT_PRESENT
    return bytes([first, 0, third, 0])


# The ASB bits of each category, as (first, second, third, fourth) byte masks (gs_la, "Notes").
_CATEGORY_BITS = {
    AsbEnabled.DRAWER: (AsbFirstByte.DRAWER_KICK_OUT_CONNECTOR_PIN_3_HIGH, 0, 0, 0),
    AsbEnabled.ONLINE_OFFLINE: (
        AsbFirstByte.OFFLINE | AsbFirstByte.COVER_OPEN | AsbFirstByte.PAPER_BEING_FED_BY_BUTTON,
        AsbSecondByte.WAITING_FOR_ONLINE_RECOVERY,
        0,
        0,
    ),
    AsbEnabled.ERROR: (
        0,
        AsbSecondByte.RECOVERABLE_ERROR
        | AsbSecondByte.AUTOCUTTER_ERROR
        | AsbSecondByte.UNRECOVERABLE_ERROR
        | AsbSecondByte.AUTO_RECOVERABLE_ERROR,
        0,
        0,
    ),
    AsbEnabled.ROLL_PAPER_SENSOR: (0, 0, AsbThirdByte.NEAR_END | AsbThirdByte.PAPER_NOT_PRESENT, 0),
    AsbEnabled.PANEL_SWITCH: (0, AsbSecondByte.PAPER_FEED_BUTTON_PUSHED, 0, 0),
}


def asb_changed(enabled: int, before: StatusState, after: StatusState) -> bool:
    """Whether a status category enabled by GS a n changed between two states."""
    old, new = asb(before), asb(after)
    return any(
        (old[i] ^ new[i]) & mask[i]
        for category, mask in _CATEGORY_BITS.items()
        if enabled & category
        for i in range(4)
    )
