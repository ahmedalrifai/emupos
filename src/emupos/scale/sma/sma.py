"""The SMA scale protocol, as a POS speaks it to a counter scale.

Source: SMA SCP-0499, "Scale Serial Communication Protocol, Levels #1 and #2", Scale
Manufacturers Association, First Edition April 1999, Mod 1 November 2005, cited section by
section below. `docs/protocols/sma.md` describes the wire format in our own words.

Framing (section 2.3): a command is LF, one command character, optional data, CR. A reply is LF,
its fields, CR. ESC (section 4.18) is the one exception: it is acted on wherever it appears.

Per connection (design D6): the About and Information pointers, whether a continuous weight is
running, and the one-shot tare error. The weight, the tare and the unit belong to the scale.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from emupos.config import ScaleUnit, SmaProfile
from emupos.scale.weights import grams_from_unit, in_unit

if TYPE_CHECKING:  # scale.py imports this module to build the protocol of a connection
    from emupos.scale.scale import ScaleOps, ScaleState

LF = 0x0A
CR = 0x0D
ESC = 0x1B
UNKNOWN_COMMAND = bytes([LF]) + b"?" + bytes([CR])  # section 5.2
WEIGHT_FIELD_WIDTH = 10  # section 5.1: the weight field is fixed at 10 characters
COMPLIANCE = "2/1.0"  # section 5.5: level 2, revision 1.0
# Section 6.2, in the order the standard lists them. I and N are left out, as section 5.6 says.
SUPPORTED_COMMANDS = "HPQRSTMCU"


class Status:
    """Scale status characters of section 5.1, the `<s>` field."""

    NONE = " "
    CENTRE_OF_ZERO = "Z"
    OVER_CAPACITY = "O"
    UNDER_CAPACITY = "U"
    ZERO_ERROR = "E"
    TARE_ERROR = "T"


ERRORS = (Status.ZERO_ERROR, Status.TARE_ERROR)


def reported_grams(state: ScaleState) -> int:
    """The net weight while a tare is set, the gross weight otherwise."""
    return state.net_grams if state.tare_grams else state.grams


def weight_field(grams: int, unit: ScaleUnit, *, high_resolution: bool) -> str:
    """The weight in `unit`, right-justified in the fixed 10 characters (section 5.1)."""
    value = in_unit(grams, unit, high_resolution=high_resolution)
    return f"{value:f}".rjust(WEIGHT_FIELD_WIDTH)


def message(
    status: str,
    gross_or_net: str,
    state: ScaleState,
    unit: ScaleUnit,
    grams: int,
    *,
    high_resolution: bool = False,
) -> bytes:
    """The standard scale response message of section 5.1.

    An error status overrides the weight with centre dashes, and overrides the centre-of-zero,
    over-capacity and under-capacity statuses, which the caller has already decided.
    """
    field = (
        "-" * WEIGHT_FIELD_WIDTH
        if status in ERRORS
        else weight_field(grams, unit, high_resolution=high_resolution)
    )
    motion = "M" if not state.stable else " "
    body = f"{status}1{gross_or_net}{motion} {field}{unit.unit}"
    return bytes([LF]) + body.encode("ascii") + bytes([CR])


def information_field(name: str, value: str) -> bytes:
    """An About or Information field: a three-character name, `:`, the value (sections 5.5, 5.6)."""
    return bytes([LF]) + f"{name:<3}:{value}".encode("ascii") + bytes([CR])


class Sma:
    def __init__(self, profile: SmaProfile) -> None:
        self._profile = profile
        self._frame = bytearray()
        self._in_frame = False
        self._repeat: str | None = None  # "W" or "H" while R or S is running
        self._repeat_at: float | None = None
        self._about: list[bytes] = []  # fields still to send, oldest first
        self._information: list[bytes] = []
        self._tare_error = False  # section 5.1: cleared after being read

    # --- the scale's side of the wire ---------------------------------------------------------

    def next_deadline(self) -> float | None:
        return self._repeat_at

    def due(self, now: float, ops: ScaleOps) -> bytes:
        """The next repeat of a continuous weight, when one is due (section 4.19)."""
        if self._repeat is None or self._repeat_at is None or now < self._repeat_at:
            return b""
        self._repeat_at = now + self._profile.repeat_interval_ms / 1000
        return self._weight(ops, high_resolution=self._repeat == "H")

    def receive(self, data: bytes, ops: ScaleOps) -> tuple[bytes, list[tuple[bytes, bytes]]]:
        """Handle received bytes, answering each complete frame.

        Returns the bytes to write and a `(request, reply)` pair for every answered frame.
        """
        written = bytearray()
        answers: list[tuple[bytes, bytes]] = []
        for byte in data:
            if byte == ESC:  # section 4.18: acted on wherever it appears, and never answered
                self._abort()
                continue
            if byte == LF:  # a new frame starts, discarding anything half-received
                self._frame.clear()
                self._in_frame = True
                continue
            if not self._in_frame:
                continue  # bytes outside a frame are not a command
            if byte != CR:
                self._frame.append(byte)
                continue
            frame, self._in_frame = bytes(self._frame), False
            self._frame.clear()
            if not frame:
                continue  # an empty frame asks nothing
            reply = self._command(frame, ops)
            written += reply
            answers.append((bytes([LF]) + frame + bytes([CR]), reply))
        return bytes(written), answers

    # --- commands -----------------------------------------------------------------------------

    def _command(self, frame: bytes, ops: ScaleOps) -> bytes:
        """Section 4: one command, already stripped of its LF and CR."""
        self._repeat, self._repeat_at = None, None  # any command ends a continuous weight
        character, argument = frame[:1], frame[1:].decode("ascii", "replace").strip()
        match character:
            case b"W" | b"P":  # 4.1, 4.3: displayed weight
                return self._weight(ops)
            case b"H" | b"Q":  # 4.2, 4.4: ten times the resolution
                return self._weight(ops, high_resolution=True)
            case b"Z":  # 4.5: zero
                return self._weight(ops, refused=not ops.zero(), error=Status.ZERO_ERROR)
            case b"T":  # 4.6, 4.7: tare the platter, or a weight the host gives
                return self._tare(argument, ops)
            case b"M":  # 4.8: report the tare weight, changing nothing
                return self._weight(ops, tare=True)
            case b"C":  # 4.9: clear the tare
                ops.clear_tare()
                return self._weight(ops)
            case b"U":  # 4.10, 4.11: cycle the unit, or select one
                if argument:
                    ops.select_unit(argument)  # section 4.11: an unknown unit is ignored
                else:
                    ops.next_unit()
                return self._weight(ops)
            case b"R" | b"S":  # 4.19: repeat until the next command
                self._repeat = "W" if character == b"R" else "H"
                self._repeat_at = ops.now() + self._profile.repeat_interval_ms / 1000
                return self._weight(ops, high_resolution=self._repeat == "H")
            case b"D":  # 4.12, 5.4: diagnostics, with nothing to report
                return bytes([LF]) + b"    " + bytes([CR])
            case b"A":  # 4.13: about this scale, and the B pointer goes back to the start
                self._about = self._about_fields()
                return information_field("SMA", COMPLIANCE)
            case b"B":  # 4.14
                return self._about.pop(0) if self._about else UNKNOWN_COMMAND
            case b"I":  # 4.15: scale information, and the N pointer goes back to the start
                self._information = self._information_fields(ops)
                return information_field("SMA", COMPLIANCE)
            case b"N":  # 4.16
                return self._information.pop(0) if self._information else UNKNOWN_COMMAND
            case _:  # 4.17 X, and anything else: section 5.2
                return UNKNOWN_COMMAND

    def _tare(self, argument: str, ops: ScaleOps) -> bytes:
        """`T` tares the platter; `T` with a weight sets that tare (sections 4.6, 4.7)."""
        grams: int | None = None
        if argument:
            try:
                grams = grams_from_unit(Decimal(argument), self._unit(ops))
            except InvalidOperation:
                return UNKNOWN_COMMAND
        return self._weight(ops, refused=not ops.tare(grams), error=Status.TARE_ERROR)

    # --- replies ------------------------------------------------------------------------------

    def _weight(
        self,
        ops: ScaleOps,
        *,
        high_resolution: bool = False,
        tare: bool = False,
        refused: bool = False,
        error: str = "",
    ) -> bytes:
        """The standard reply, formed after any operation has been applied."""
        state, unit = ops.state(), self._unit(ops)
        status = self._status(state, refused=refused, error=error)
        if tare:
            return message(status, "T", state, unit, state.tare_grams)
        gross_or_net = "N" if state.tare_grams else "G"
        return message(
            status,
            gross_or_net.lower() if high_resolution else gross_or_net,
            state,
            unit,
            reported_grams(state),
            high_resolution=high_resolution,
        )

    def _status(self, state: ScaleState, *, refused: bool, error: str) -> str:
        """The `<s>` field: an error if one applies, otherwise what the weight says."""
        if refused:
            if error == Status.TARE_ERROR:
                self._tare_error = True  # section 5.1: it is reported once, then cleared
            return error
        if self._tare_error:
            self._tare_error = False
            return Status.NONE if state.grams != 0 else Status.CENTRE_OF_ZERO
        if state.grams > state.capacity_grams:
            return Status.OVER_CAPACITY
        if reported_grams(state) < 0:
            return Status.UNDER_CAPACITY
        if state.grams == 0:
            return Status.CENTRE_OF_ZERO
        return Status.NONE

    def _about_fields(self) -> list[bytes]:
        """Section 5.5, in the order the B command sends them."""
        fields = [
            ("MFG", self._profile.maker),
            ("MOD", self._profile.model),
            ("REV", self._profile.revision),
        ]
        if self._profile.serial_number is not None:
            fields.append(("SN_", self._profile.serial_number))
        fields.append(("END", ""))
        return [information_field(name, value) for name, value in fields]

    def _information_fields(self, ops: ScaleOps) -> list[bytes]:
        """Section 5.6, in the order the N command sends them."""
        unit = self._unit(ops)
        capacity = in_unit(self._profile.capacity_grams, unit)
        fields = [
            ("TYP", "S"),  # a scale, not a weight classifier
            ("CAP", f"{unit.unit}:{capacity:f}:{unit.count_by}:{unit.decimals}"),
            ("CMD", SUPPORTED_COMMANDS),
            ("END", ""),
        ]
        return [information_field(name, value) for name, value in fields]

    def _unit(self, ops: ScaleOps) -> ScaleUnit:
        """The unit the scale reports in. An SMA profile always lists at least one."""
        return ops.unit() or self._profile.units[0]

    def _abort(self) -> None:
        """ESC: forget what the host was in the middle of, and stop talking (section 4.18)."""
        self._frame.clear()
        self._in_frame = False
        self._repeat, self._repeat_at = None, None
        self._about, self._information = [], []
