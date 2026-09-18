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
            warn_scan_not_typed(scanner.device_id, accepted, len(scan.keys))
            scanner.failed(scan.id)
            return
    except BaseException:
        scanner.failed(scan.id)
        raise
    apply(scanner.device_id, scanner.finished(scan.id))


def warn_scan_not_typed(
    device_id: str, keys_accepted: int | None, total: int, reason: str | None = None
) -> None:
    """The warning the `emupos run` output must carry for a scan that was not typed.

    Both typing paths use it: `deliver_scan` when emupos typed, and a client's failed report
    when it typed (barcode-scanner spec, "Windows privilege limitation").
    """
    if keys_accepted is None:
        logger.warning("%s: the scan was not typed: %s", device_id, reason or "no reason given")
        return
    logger.warning(
        "%s: the operating system accepted %d of %d keystrokes; on Windows, keystrokes do not "
        "reach a window running with higher privileges than the process that types",
        device_id,
        keys_accepted,
        total,
    )
