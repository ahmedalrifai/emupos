"""Delivering an accepted scan after its countdown: as keystrokes, or as bytes on serial connections."""

import asyncio
import logging
from collections.abc import Callable

from emupos.daemon.runtime import DeviceRuntime
from emupos.events import Output
from emupos.scanner.scanner import AcceptedScan, Scanner
from emupos.transports.keyboard.keyboard import Keyboard, type_keys

logger = logging.getLogger("emupos")


async def deliver_scan(
    runtime: DeviceRuntime,
    scanner: Scanner,
    scan: AcceptedScan,
    keyboard: Keyboard | None,
    *,
    now: Callable[[], float],
    apply: Callable[[str, Output], None],
) -> None:
    """Wait for the countdown, deliver, then publish `scanner.scan.delivered` (or free the scanner)."""
    try:
        await asyncio.sleep(max(0.0, scan.deliver_at - now()))
        if keyboard is None:
            for writer in runtime.writers.values():
                writer.write(scan.serial_bytes)
                await writer.drain()
        elif (accepted := await type_keys(keyboard, scan.keys, scanner.inter_key_delay_ms)) < len(
            scan.keys
        ):
            logger.warning(
                "%s: the operating system accepted %d of %d keystrokes; on Windows, keystrokes "
                "do not reach a window running with higher privileges than emupos",
                scanner.device_id,
                accepted,
                len(scan.keys),
            )
            scanner.failed(scan.id)
            return
    except BaseException:
        scanner.failed(scan.id)
        raise
    apply(scanner.device_id, scanner.finished(scan.id))
