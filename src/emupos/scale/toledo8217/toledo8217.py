"""Mettler Toledo 8217 scale protocol, as spoken to POS clients.

Source: the weight-scale spec of openspec change bootstrap-emupos-v0-1, which records the wire
contract that common POS clients (e.g. Odoo's public Toledo 8217 driver) rely on. Each handled
byte below cites the spec requirement it implements.

Pure (design D2): bytes and a `ScaleState` in, reply bytes out. Replies are computed as soon as
the bytes are received, so meeting "within 100 ms" is up to the transport alone.

Weight rounding: the weight reply gives the reported weight rounded to the nearest multiple of
the profile's `division_grams`, ties away from zero (1252 g -> 1.250 kg, 1253 g -> 1.255 kg with
5 g divisions). The motion, over-capacity, under-zero and center-of-zero conditions are judged
on the exact grams, never on the rounded value, so 15001 g is over a 15000 g capacity.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import IntFlag
from typing import TYPE_CHECKING

from emupos.config import Toledo8217Profile

if TYPE_CHECKING:  # scale.py imports this module to build the protocol of a connection
    from emupos.scale.scale import ScaleReading, ScaleState

STX = 0x02
CR = 0x0D
LF = 0x0A
WEIGHT_REQUEST = ord("W")
ECHO_START = ord("E")
ECHO_END = ord("F")
ECHO_REPLY = bytes.fromhex("02 45 0d")


class Status(IntFlag):
    """Status byte bits ("Status reply when the weight cannot be reported").

    Bit 3 and bit 7 are never set, so the byte is always 7-bit and can never be CR or LF.
    """

    IN_MOTION = 1 << 0
    OVER_CAPACITY = 1 << 1
    UNDER_ZERO = 1 << 2
    CENTER_OF_ZERO = 1 << 4
    NET_WEIGHT = 1 << 5
    BAD_COMMAND = 1 << 6


NOT_REPORTABLE = Status.IN_MOTION | Status.OVER_CAPACITY | Status.UNDER_ZERO


def reported_grams(state: ScaleState) -> int:
    """The net weight while a tare is set, the gross weight otherwise ("Scale weight state")."""
    return state.net_grams if state.tare_grams else state.grams


def status(state: ScaleState) -> Status:
    """Every status bit that applies to the state; `BAD_COMMAND` is added by the caller."""
    flags = Status(0)
    if not state.stable:
        flags |= Status.IN_MOTION
    if state.grams > state.capacity_grams:
        flags |= Status.OVER_CAPACITY
    if reported_grams(state) < 0:
        flags |= Status.UNDER_ZERO
    if state.grams == 0:
        flags |= Status.CENTER_OF_ZERO
    if state.tare_grams:
        flags |= Status.NET_WEIGHT
    return flags


def status_reply(flags: Status) -> bytes:
    """STX `?` status-byte CR."""
    return bytes([STX, ord("?"), flags, CR])


def kilograms(grams: int, profile: Toledo8217Profile) -> str:
    """Grams as the kilogram text of a weight reply, e.g. 1250 g -> `01.250` (never truncated)."""
    divisions = (Decimal(grams) / profile.division_grams).quantize(Decimal(1), ROUND_HALF_UP)
    decimals = profile.reply_decimals
    value = (divisions * profile.division_grams).scaleb(-3)
    value = value.quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    width = profile.reply_integer_digits + (decimals + 1 if decimals else 0)
    return f"{value:0{width}f}"


def weight_reply(state: ScaleState, profile: Toledo8217Profile) -> bytes:
    """The reply to `W`: the weight when it can be reported, a status reply otherwise."""
    flags = status(state)
    if flags & NOT_REPORTABLE:
        return status_reply(flags)
    net = b"N" if state.tare_grams else b""
    return (
        bytes([STX]) + kilograms(reported_grams(state), profile).encode("ascii") + net + bytes([CR])
    )


class Toledo8217:
    """Protocol state of one connection: echo mode is per connection."""

    def __init__(self, profile: Toledo8217Profile) -> None:
        self._profile = profile
        self._echoing = False

    def next_deadline(self) -> float | None:
        """Toledo 8217 only ever answers what it is asked."""
        return None

    def due(self, now: float, ops: ScaleReading) -> bytes:
        return b""

    def receive(self, data: bytes, ops: ScaleReading) -> tuple[bytes, list[tuple[bytes, bytes]]]:
        """Handle received bytes one at a time.

        Returns the bytes to write and a `(request, reply)` pair for every answered request.
        Echoed bytes are written but are not answered requests ("Request events").
        """
        state = ops.state()
        written = bytearray()
        answers: list[tuple[bytes, bytes]] = []
        for byte in data:
            if self._echoing:
                # "Echo probe": echo unchanged until F, which ends the probe without a reply.
                if byte == ECHO_END:
                    self._echoing = False
                else:
                    written.append(byte)
                continue
            if byte in (CR, LF):
                continue  # "Unrecognised commands": line terminators between commands are ignored
            if byte == WEIGHT_REQUEST:  # "Weight request with a reportable weight"
                reply = weight_reply(state, self._profile)
            elif byte == ECHO_START:  # "Echo probe"
                reply = ECHO_REPLY
                self._echoing = True
            else:  # "Unrecognised commands"
                reply = status_reply(status(state) | Status.BAD_COMMAND)
            written += reply
            answers.append((bytes([byte]), reply))
        return bytes(written), answers
