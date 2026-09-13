"""Barcode scanner: scan requests, one scan at a time, and what each scan delivers
(barcode-scanner spec).

Pure (design D2): the daemon passes `now` (monotonic seconds), waits until `deliver_at`,
writes `serial_bytes` or types `keys`, then reports back with `finished` or `failed`. In
keyboard mode the daemon checks the OS keyboard is ready before calling `request`.
"""

import unicodedata
from dataclasses import dataclass
from typing import Literal

from emupos.events import NO_OUTPUT, Event, EventType, Output
from emupos.scanner.keys import US_LAYOUT, Key, Suffix, plan_keys

type Mode = Literal["keyboard", "serial"]

SERIAL_SUFFIX: dict[Suffix, bytes] = {
    "enter": bytes.fromhex("0d"),
    "tab": bytes.fromhex("09"),
    "none": b"",
}


class ScanRejectedError(Exception):
    """A scan request was refused; nothing is delivered.

    `conflict` False: the request itself is invalid (API 422, `validation_error`).
    `conflict` True: the scanner cannot take it now (API 409 with `code`).
    """

    def __init__(self, code: str, message: str, fix: str | None, conflict: bool) -> None:
        self.code = code
        self.message = message
        self.fix = fix
        self.conflict = conflict
        super().__init__(f"{message}; {fix}" if fix else message)


@dataclass(frozen=True, slots=True)
class AcceptedScan:
    id: str  # "<device id>-<n>", unique for the run
    data: str
    mode: Mode
    unicode: bool
    deliver_at: float  # monotonic seconds; delivery starts no earlier
    serial_bytes: bytes  # serial mode: data as UTF-8 plus the suffix byte; b"" in keyboard mode
    keys: tuple[Key, ...]  # keyboard mode: each key then the suffix key; () in serial mode


class Scanner:
    def __init__(self, device_id: str, mode: Mode, suffix: Suffix, inter_key_delay_ms: int) -> None:
        self.device_id = device_id
        self.mode: Mode = mode
        self.suffix: Suffix = suffix
        self.inter_key_delay_ms = inter_key_delay_ms
        self._in_progress: AcceptedScan | None = None
        self._count = 0

    @property
    def busy(self) -> bool:
        return self._in_progress is not None

    def request(self, data: str, countdown_seconds: int, unicode: bool, now: float) -> AcceptedScan:
        """Validate and accept a scan. Raises ScanRejectedError."""
        self._validate(data, countdown_seconds, unicode)
        if self._in_progress is not None:
            raise ScanRejectedError(
                "scan_in_progress",
                f"a scan is already in progress on {self.device_id}",
                "wait for its scanner.scan.delivered event, then scan again",
                conflict=True,
            )
        self._count += 1
        keyboard = self.mode == "keyboard"
        scan = AcceptedScan(
            id=f"{self.device_id}-{self._count}",
            data=data,
            mode=self.mode,
            unicode=unicode,
            deliver_at=now + countdown_seconds,
            serial_bytes=b"" if keyboard else data.encode("utf-8") + SERIAL_SUFFIX[self.suffix],
            keys=plan_keys(data, self.suffix, unicode) if keyboard else (),
        )
        self._in_progress = scan
        return scan

    def finished(self, scan_id: str) -> Output:
        """The scan and its suffix were delivered: publish its one delivery event."""
        scan = self._in_progress
        if scan is None or scan.id != scan_id:  # already reported, or not this scanner's scan
            return NO_OUTPUT
        self._in_progress = None
        data = {"id": scan.id, "data": scan.data, "mode": scan.mode}
        return Output(events=(Event(EventType.SCANNER_SCAN_DELIVERED, self.device_id, data),))

    def failed(self, scan_id: str) -> None:
        """The scan was not (fully) delivered: free the scanner without an event."""
        if self._in_progress is not None and self._in_progress.id == scan_id:
            self._in_progress = None

    def _validate(self, data: str, countdown_seconds: int, unicode: bool) -> None:
        if not data:
            raise _invalid("`data` must not be empty", "send the barcode text in `data`")
        if countdown_seconds < 0:
            raise _invalid(
                "`countdown_seconds` must be 0 or more",
                "use 0 to deliver immediately, or leave it out for the 3-second default",
            )
        try:
            data.encode("utf-8")
        except UnicodeEncodeError:  # a lone surrogate, e.g. "\ud800" in JSON
            raise _invalid(
                "`data` is not valid Unicode text", "remove unpaired surrogates"
            ) from None
        if self.mode != "keyboard":
            return
        for char in data:
            if not unicode and char not in US_LAYOUT:
                raise _invalid(
                    f"`data` contains {char!r} (U+{ord(char):04X}); without unicode, keyboard mode "
                    "types only printable ASCII keys of the US layout",
                    "send `unicode: true` (or use `--unicode` with `emupos scan`) to type exact characters",
                )
            if unicodedata.category(char) == "Cc":
                raise _invalid(
                    f"`data` contains the control character U+{ord(char):04X}, which cannot be typed",
                    "remove it; the scanner's `suffix` setting adds Enter or Tab",
                )


def _invalid(message: str, fix: str) -> ScanRejectedError:
    return ScanRejectedError("validation_error", message, fix, conflict=False)
