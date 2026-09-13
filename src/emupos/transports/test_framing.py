import asyncio
import os
import sys
from pathlib import Path

import pytest

from emupos.config import SerialFraming
from emupos.transports.framing import (
    Mismatch,
    ObservedFraming,
    framing_mismatches,
    observe_framing,
    watch_framing,
)
from emupos.transports.pty import open_pty

if sys.platform != "win32":
    import termios
    import tty

TOLEDO = SerialFraming(baud=9600, data_bits=7, parity="even", stop_bits=1)


def test_matching_framing_has_no_mismatches() -> None:
    assert framing_mismatches(TOLEDO, ObservedFraming(9600, 7, "even")) == ()


def test_each_differing_setting_is_listed() -> None:
    assert framing_mismatches(TOLEDO, ObservedFraming(19200, 8, "none")) == (
        Mismatch("baud", 9600, 19200),
        Mismatch("data_bits", 7, 8),
        Mismatch("parity", "even", "none"),
    )


def test_unobserved_settings_are_not_compared() -> None:
    assert framing_mismatches(TOLEDO, ObservedFraming(9600, None, None)) == ()


# Real ptys exist on macOS and Linux only.
if sys.platform != "win32":

    def set_client_framing(fd: int, baud: int) -> None:
        """What a POS does: raw 8N1 at `baud`."""
        tty.setraw(fd)
        attributes = termios.tcgetattr(fd)
        attributes[4] = attributes[5] = getattr(termios, f"B{baud}")
        termios.tcsetattr(fd, termios.TCSANOW, attributes)

    async def test_port_starts_at_the_expected_framing(tmp_path: Path) -> None:
        # 38400 is the Linux pty default, so there only the data bits and parity would change,
        # which glibc rejects with EINVAL.
        expected = SerialFraming(baud=38400, data_bits=7, parity="even", stop_bits=1)
        port = await open_pty("deli", expected, tmp_path)
        try:
            assert framing_mismatches(expected, observe_framing(port.slave_fd)) == ()
        finally:
            await port.close()

    @pytest.mark.skipif(sys.platform != "darwin", reason="only macOS exposes data bits and parity")
    async def test_macos_observes_data_bits_and_parity(tmp_path: Path) -> None:
        port = await open_pty("deli", TOLEDO, tmp_path)
        client = os.open(port.link_path, os.O_RDWR | os.O_NOCTTY)
        try:
            set_client_framing(client, 9600)
            assert framing_mismatches(TOLEDO, observe_framing(port.slave_fd)) == (
                Mismatch("data_bits", 7, 8),
                Mismatch("parity", "even", "none"),
            )
        finally:
            os.close(client)
            await port.close()

    @pytest.mark.skipif(sys.platform != "linux", reason="Linux-specific pty behaviour")
    async def test_linux_observes_baud_only(tmp_path: Path) -> None:
        port = await open_pty("deli", TOLEDO, tmp_path)
        client = os.open(port.link_path, os.O_RDWR | os.O_NOCTTY)
        try:
            set_client_framing(client, 19200)
            assert observe_framing(port.slave_fd) == ObservedFraming(19200, None, None)
        finally:
            os.close(client)
            await port.close()

    async def test_watcher_reports_a_mismatching_framing_once(tmp_path: Path) -> None:
        port = await open_pty("deli", TOLEDO, tmp_path)
        client = os.open(port.link_path, os.O_RDWR | os.O_NOCTTY)
        reports: list[tuple[Mismatch, ...]] = []
        watcher = asyncio.create_task(watch_framing(port.slave_fd, TOLEDO, reports.append, 0.01))
        try:
            await asyncio.sleep(0.05)
            assert reports == []  # nothing before a client changes the framing

            set_client_framing(client, 19200)
            await asyncio.sleep(0.2)  # many polls, same framing

            assert len(reports) == 1
            assert Mismatch("baud", 9600, 19200) in reports[0]
        finally:
            watcher.cancel()
            os.close(client)
            await port.close()
