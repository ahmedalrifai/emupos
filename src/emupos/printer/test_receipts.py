from datetime import UTC, datetime, timedelta
from pathlib import Path

from emupos.printer.escpos.render import RenderedReceipt
from emupos.printer.receipts import ReceiptStore

AT = datetime(2026, 9, 13, 12, 4, 51, 123456, tzinfo=UTC)


def receipt(text: str = "Hi\n") -> RenderedReceipt:
    return RenderedReceipt(b"\x89PNG fake", text, 576, 24, "cut")


def test_completed_job_is_stored(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "receipts")

    meta = store.save("front", receipt(), AT)

    assert meta.id.startswith("front-20260913T120451123Z-")
    assert (meta.device_id, meta.width_dots, meta.height_dots, meta.boundary) == (
        "front",
        576,
        24,
        "cut",
    )
    assert sorted(p.suffix for p in (tmp_path / "receipts").iterdir()) == [".json", ".png", ".txt"]
    assert store.get("front", meta.id) == meta
    assert store.image("front", meta.id) == b"\x89PNG fake"
    assert store.text("front", meta.id) == "Hi\n"


def test_same_instant_never_collides(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path)

    ids = {store.save("front", receipt(), AT).id for _ in range(50)}

    assert len(ids) == 50


def test_two_printers_share_a_receipts_directory(tmp_path: Path) -> None:
    front, back = ReceiptStore(tmp_path), ReceiptStore(tmp_path)

    a = front.save("front", receipt("A\n"), AT)
    b = back.save("back", receipt("B\n"), AT)

    assert [m.id for m in front.list("front")] == [a.id]
    assert [m.id for m in front.list("back")] == [b.id]
    assert front.text("back", b.id) == "B\n"
    assert front.get("front", b.id) is None  # not retrievable under another device id


def test_prefix_of_another_device_id_is_not_listed(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path)
    store.save("front-2", receipt(), AT)

    assert store.list("front") == []


def test_latest_matches_the_first_entry_of_the_list(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path)
    for minutes in (0, 2, 1):
        store.save("front", receipt(), AT + timedelta(minutes=minutes))

    receipts = store.list("front")

    assert len(receipts) == 3
    assert [m.completed_at.minute for m in receipts] == [6, 5, 4]
    assert store.get("front", "latest") == receipts[0]


def test_receipts_survive_a_new_store_on_the_same_directory(tmp_path: Path) -> None:
    meta = ReceiptStore(tmp_path).save("front", receipt(), AT)

    assert ReceiptStore(tmp_path).get("front", "latest") == meta


def test_no_receipts_yet(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "missing")

    assert store.list("front") == []
    assert store.get("front", "latest") is None
    assert store.text("front", "latest") is None
    assert store.image("front", "latest") is None


def test_unknown_or_malicious_ids_are_not_found(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path)
    store.save("front", receipt(), AT)

    assert store.get("front", "front-20260913T120451123Z-00000000") is None
    assert store.get("front", "../../etc/passwd") is None
    assert store.text("front", "nope") is None
