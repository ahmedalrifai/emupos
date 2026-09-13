"""Golden rendering cases: every cases/**/input.hex against its expected.png and expected.txt.

Missing expected files are written on the first run. After an intended rendering change,
regenerate them all and review the diff:

    EMUPOS_UPDATE_CASES=1 uv run pytest src/emupos/printer/escpos/test_cases.py
"""

import io
import os
from pathlib import Path

import pytest
from PIL import Image

from emupos.printer.test_support import Pos

CASES = Path(__file__).parent / "cases"
UPDATE = os.environ.get("EMUPOS_UPDATE_CASES") == "1"


def _case_directories() -> list[Path]:
    return sorted(path.parent for path in CASES.rglob("input.hex"))


@pytest.mark.parametrize("case", _case_directories(), ids=lambda path: str(path.relative_to(CASES)))
def test_case_renders_as_expected(case: Path) -> None:
    pos = Pos("epson-tm-t20iii")
    pos.send((case / "input.hex").read_text())
    pos.close()
    assert len(pos.receipts) <= 1, "a case holds at most one job; split it into several cases"
    receipt = pos.receipts[0] if pos.receipts else None
    text = receipt.text if receipt else ""  # no receipt: an empty text dump and no image

    expected_png, expected_txt = case / "expected.png", case / "expected.txt"
    if UPDATE or not expected_txt.exists():
        expected_txt.write_text(text, encoding="utf-8", newline="\n")
        expected_png.unlink(missing_ok=True)
        if receipt:
            expected_png.write_bytes(receipt.png)

    assert text == expected_txt.read_text(encoding="utf-8")
    assert expected_png.exists() == (receipt is not None)
    if receipt:
        # Compare dots, not PNG bytes: compression output may differ between zlib versions.
        actual = Image.open(io.BytesIO(receipt.png)).convert("1")
        expected = Image.open(expected_png).convert("1")
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes(), f"dots differ from {expected_png}"
