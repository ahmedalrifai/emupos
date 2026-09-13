"""Completed receipts on disk: `<id>.png`, `<id>.txt` and `<id>.json` (metadata) per receipt.

Ids look like `front-20260913T120451123Z-9f86d081`: device id, completion time in UTC and a
random suffix, so receipts never collide across runs or between printers sharing a
directory. Each file is written to a temporary name and renamed, so readers never see a
partial file; the metadata file is written last and makes the receipt visible.
"""

import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from emupos.printer.escpos.render import Boundary, RenderedReceipt

LATEST = "latest"
_ID = re.compile(r"^[a-z0-9][a-z0-9-]*-\d{8}T\d{9}Z-[0-9a-f]{8}$")


@dataclass(frozen=True, slots=True)
class ReceiptMeta:
    id: str
    device_id: str
    completed_at: datetime
    width_dots: int
    height_dots: int
    boundary: Boundary


class ReceiptStore:
    def __init__(self, receipts_dir: Path) -> None:
        self.directory = receipts_dir

    def save(self, device_id: str, receipt: RenderedReceipt, completed_at: datetime) -> ReceiptMeta:
        self.directory.mkdir(parents=True, exist_ok=True)
        utc = completed_at.astimezone(UTC)
        stamp = utc.replace(microsecond=utc.microsecond // 1000 * 1000)  # kept to milliseconds
        prefix = f"{device_id}-{stamp:%Y%m%dT%H%M%S}{stamp.microsecond // 1000:03d}Z"
        receipt_id = f"{prefix}-{secrets.token_hex(4)}"
        while self._path(receipt_id, ".json").exists():  # ponytail: 32 random bits; retry is enough
            receipt_id = f"{prefix}-{secrets.token_hex(4)}"
        meta = ReceiptMeta(
            receipt_id, device_id, stamp, receipt.width_dots, receipt.height_dots, receipt.boundary
        )
        self._write(receipt_id, ".png", receipt.png)
        self._write(receipt_id, ".txt", receipt.text.encode("utf-8"))
        self._write(receipt_id, ".json", json.dumps(_to_json(meta), indent=2).encode("utf-8"))
        return meta

    def list(self, device_id: str) -> list[ReceiptMeta]:
        """The printer's receipts, newest first."""
        # ponytail: reads every metadata file per call; add an index if directories get huge
        metas = (self._read_meta(path) for path in self.directory.glob(f"{device_id}-*.json"))
        mine = [meta for meta in metas if meta is not None and meta.device_id == device_id]
        return sorted(mine, key=lambda meta: (meta.completed_at, meta.id), reverse=True)

    def get(self, device_id: str, receipt_id: str) -> ReceiptMeta | None:
        """One receipt's metadata; `latest` is the newest. None when there is no such receipt."""
        if receipt_id == LATEST:
            receipts = self.list(device_id)
            return receipts[0] if receipts else None
        if not _ID.match(receipt_id):  # ids come from API paths: never build a path from others
            return None
        meta = self._read_meta(self._path(receipt_id, ".json"))
        return meta if meta is not None and meta.device_id == device_id else None

    def image(self, device_id: str, receipt_id: str) -> bytes | None:
        """The PNG image, or None when there is no such receipt."""
        meta = self.get(device_id, receipt_id)
        return None if meta is None else self._path(meta.id, ".png").read_bytes()

    def text(self, device_id: str, receipt_id: str) -> str | None:
        """The UTF-8 text dump, or None when there is no such receipt."""
        meta = self.get(device_id, receipt_id)
        return None if meta is None else self._path(meta.id, ".txt").read_text(encoding="utf-8")

    def _path(self, receipt_id: str, suffix: str) -> Path:
        return self.directory / f"{receipt_id}{suffix}"

    def _write(self, receipt_id: str, suffix: str, data: bytes) -> None:
        with tempfile.NamedTemporaryFile(dir=self.directory, suffix=".tmp", delete=False) as file:
            file.write(data)
        os.replace(file.name, self._path(receipt_id, suffix))

    def _read_meta(self, path: Path) -> ReceiptMeta | None:
        try:
            raw = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
            return ReceiptMeta(
                id=str(raw["id"]),
                device_id=str(raw["device_id"]),
                completed_at=datetime.fromisoformat(str(raw["completed_at"])),
                width_dots=int(cast(int, raw["width_dots"])),
                height_dots=int(cast(int, raw["height_dots"])),
                boundary=cast(Boundary, raw["boundary"]),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None  # missing, or not a receipt written by this store


def _to_json(meta: ReceiptMeta) -> dict[str, object]:
    return {
        "id": meta.id,
        "device_id": meta.device_id,
        "completed_at": meta.completed_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "width_dots": meta.width_dots,
        "height_dots": meta.height_dots,
        "boundary": meta.boundary,
    }
