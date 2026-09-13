"""Serial framing: the framing a device expects versus the framing a client set on a pty."""

import asyncio
import errno
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from emupos.config import SerialFraming

if sys.platform != "win32":
    import termios

    # termios speed constants equal the baud rate on macOS but are small codes on Linux (B9600 == 13).
    _BAUD_BY_SPEED = {
        getattr(termios, name): int(name[1:])
        for name in dir(termios)
        if name.startswith("B") and name[1:].isdigit()
    }


@dataclass(frozen=True, slots=True)
class ObservedFraming:
    baud: int
    data_bits: int | None  # None where the OS does not expose the value
    parity: Literal["none", "even", "odd"] | None


@dataclass(frozen=True, slots=True)
class Mismatch:
    setting: str  # "baud", "data_bits" or "parity"
    expected: int | str
    observed: int | str


def framing_mismatches(expected: SerialFraming, observed: ObservedFraming) -> tuple[Mismatch, ...]:
    """Compare only the settings that were observed."""
    settings = (
        ("baud", expected.baud, observed.baud),
        ("data_bits", expected.data_bits, observed.data_bits),
        ("parity", expected.parity, observed.parity),
    )
    return tuple(
        Mismatch(name, want, got) for name, want, got in settings if got is not None and got != want
    )


def apply_framing(fd: int, framing: SerialFraming) -> None:
    """Set the terminal at `fd` to `framing`, leaving its other settings (such as raw mode) as they are."""
    if sys.platform == "win32":
        raise NotImplementedError("serial framing can only be set on macOS and Linux")
    attributes = termios.tcgetattr(fd)
    kept_bits = attributes[2] & (termios.CSIZE | termios.PARENB | termios.PARODD)
    sizes = {5: termios.CS5, 6: termios.CS6, 7: termios.CS7, 8: termios.CS8}
    cflag = attributes[2] & ~(termios.CSIZE | termios.PARENB | termios.PARODD | termios.CSTOPB)
    # CLOCAL: a simulated device never waits for carrier detect, which real adapters may not wire.
    cflag |= sizes[framing.data_bits] | termios.CLOCAL | termios.CREAD
    if framing.parity != "none":
        cflag |= termios.PARENB
    if framing.parity == "odd":
        cflag |= termios.PARODD
    if framing.stop_bits == 2:
        cflag |= termios.CSTOPB
    attributes[2] = cflag
    speed = getattr(termios, f"B{framing.baud}", None)
    if speed is not None:  # a non-standard rate keeps the current speed
        attributes[4] = attributes[5] = speed
    try:
        termios.tcsetattr(fd, termios.TCSANOW, attributes)
    except termios.error as error:
        # Linux ptys force 8 data bits without parity, and tcsetattr then fails with EINVAL if
        # nothing else changed. Real UARTs honour the bits, so this retry only happens on ptys.
        if sys.platform != "linux" or error.args[0] != errno.EINVAL:
            raise
        attributes[2] = cflag & ~(termios.CSIZE | termios.PARENB | termios.PARODD) | kept_bits
        termios.tcsetattr(fd, termios.TCSANOW, attributes)


def observe_framing(fd: int) -> ObservedFraming:
    """Read the framing a client configured on the pty, e.g. from `PtyPort.slave_fd`."""
    if sys.platform == "win32":
        raise NotImplementedError("serial framing can only be observed on macOS and Linux ptys")
    _, _, cflag, _, _, ospeed, _ = termios.tcgetattr(fd)
    baud = _BAUD_BY_SPEED.get(ospeed, int(ospeed))
    if sys.platform == "linux":
        # The Linux pty driver forces CS8 and clears PARENB whatever the client sets.
        return ObservedFraming(baud, None, None)
    sizes = {termios.CS5: 5, termios.CS6: 6, termios.CS7: 7, termios.CS8: 8}
    parity = ("odd" if cflag & termios.PARODD else "even") if cflag & termios.PARENB else "none"
    return ObservedFraming(baud, sizes[cflag & termios.CSIZE], parity)


async def watch_framing(
    fd: int,
    expected: SerialFraming,
    on_mismatch: Callable[[tuple[Mismatch, ...]], None],
    interval: float = 0.2,
) -> None:
    """Poll until cancelled, calling `on_mismatch` once each time the framing changes to one
    that mismatches. Cancel this task before closing `fd`."""
    last: ObservedFraming | None = None
    while True:
        observed = observe_framing(fd)
        if observed != last:
            last = observed
            if mismatches := framing_mismatches(expected, observed):
                on_mismatch(mismatches)
        await asyncio.sleep(interval)
