"""Bar patterns for GS k barcodes and module matrices for GS ( k QR codes.

Patterns come from python-barcode and segno; this module only adapts the data forms the
Epson reference defines and scales modules to whole dots.
- GS k: https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lk.html
- GS w: https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lw.html
- GS ( k QR code: https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lparen_lk.html
"""

from dataclasses import dataclass

import segno
from barcode import EAN8, EAN13, ITF, Code39
from barcode.charsets import code128
from barcode.errors import BarcodeError
from PIL import Image

from emupos.printer.escpos.render import scale

# GS k m: Function A (m = 0-6) and Function B (m = 65-79) name the same symbologies.
SYMBOLOGIES: dict[int, str] = {
    0: "UPC-A", 1: "UPC-E", 2: "EAN-13", 3: "EAN-8", 4: "CODE39", 5: "ITF", 6: "CODABAR",
    65: "UPC-A", 66: "UPC-E", 67: "EAN-13", 68: "EAN-8", 69: "CODE39", 70: "ITF", 71: "CODABAR",
    72: "CODE93", 73: "CODE128", 74: "GS1-128", 75: "GS1 DataBar Omnidirectional",
    76: "GS1 DataBar Truncated", 77: "GS1 DataBar Limited", 78: "GS1 DataBar Expanded",
    79: "CODE128 auto",
}  # fmt: skip

# GS w n (n = 2-6): module width in dots; for CODE39 and ITF ("binary level") n is the thin
# element width and this table gives the thick element width.
THICK_ELEMENT_DOTS = {2: 5, 3: 8, 4: 10, 5: 13, 6: 15}


@dataclass(frozen=True, slots=True)
class Bars:
    """A 1D barcode: element widths in dots, alternating bar and space, starting with a bar."""

    widths: tuple[int, ...]
    hri: str  # the human readable interpretation printed with GS H

    def image(self, height: int) -> Image.Image:
        row = bytearray()
        for index, width in enumerate(self.widths):
            row += (b"\x00" if index % 2 == 0 else b"\xff") * width
        return scale(Image.frombytes("L", (len(row), 1), bytes(row)).convert("1"), 1, height)


def barcode(symbology: str, data: bytes, module_width: int) -> Bars | None:
    """The bars of a GS k barcode, or None when the symbology or data is not supported."""
    text = data.decode("latin-1")
    try:
        match symbology:
            case "EAN-13" | "UPC-A":
                # UPC-A is EAN-13 with a leading 0. A check digit sent by the POS is not checked.
                digits = text if symbology == "EAN-13" else "0" + text
                if not digits.isdigit() or len(digits) not in (12, 13):
                    return None
                code = EAN13(digits, no_checksum=len(digits) == 13)
                full = code.get_fullcode()
                return _modules(
                    code.build()[0], module_width, full if symbology == "EAN-13" else full[1:]
                )
            case "EAN-8":
                if not text.isdigit() or len(text) not in (7, 8):
                    return None
                code = EAN8(text, no_checksum=len(text) == 8)
                return _modules(code.build()[0], module_width, code.get_fullcode())
            case "CODE39":
                text = text.strip("*")  # the printer adds the start and stop characters
                pattern = Code39(text, add_checksum=False).build()[0]
                return _thin_and_thick(pattern, 1, module_width, f"*{text}*")
            case "ITF":
                text = text[: len(text) // 2 * 2]  # an odd last digit is ignored
                if not text.isdigit():
                    return None
                return _thin_and_thick(
                    ITF(text, narrow=1, wide=2).build()[0], 1, module_width, text
                )
            case "CODE128":
                return _code128(data, module_width)
            case _:
                return None
    except BarcodeError:
        return None


def qr_code(data: bytes, error_correction: str, module_size: int) -> Image.Image | None:
    """A model 2 QR code with modules of `module_size` dots, or None if the data does not fit."""
    try:
        qr = segno.make_qr(data, error=error_correction, boost_error=False)
    except segno.DataOverflowError:
        return None
    size = len(qr.matrix)
    dots = bytes(0 if dark else 255 for row in qr.matrix for dark in row)
    return scale(Image.frombytes("L", (size, size), dots).convert("1"), module_size, module_size)


def _modules(pattern: str, module_width: int, hri: str) -> Bars:
    """Multi-level symbologies: every module is `module_width` dots."""
    return Bars(tuple(len(run) * module_width for run in _runs(pattern)), hri)


def _thin_and_thick(pattern: str, thin_run: int, module_width: int, hri: str) -> Bars:
    """Binary-level symbologies: runs of `thin_run` modules are thin elements, longer are thick."""
    thick = THICK_ELEMENT_DOTS[module_width]
    return Bars(
        tuple(module_width if len(run) == thin_run else thick for run in _runs(pattern)), hri
    )


def _runs(pattern: str) -> list[str]:
    runs: list[str] = []
    for module in pattern:
        if runs and runs[-1][0] == module:
            runs[-1] += module
        else:
            runs.append(module)
    return runs


# CODE128 symbol values (gs_lk, "Notes for CODE128"): data starts with a code set selection
# "{A", "{B" or "{C"; "{" introduces the special characters below; "{{" is a literal "{".
# ponytail: SHIFT ("{S") is not supported; such barcodes are reported, not drawn.
_CODE_SETS = {ord("A"): 103, ord("B"): 104, ord("C"): 105}  # start codes
_SWITCH = {ord("A"): 101, ord("B"): 100, ord("C"): 99}
_FNC = {ord("1"): 102, ord("2"): 97, ord("3"): 96}


def _code128(data: bytes, module_width: int) -> Bars | None:
    if len(data) < 2 or data[0] != ord("{") or data[1] not in _CODE_SETS:
        return None
    code_set = data[1]
    values = [_CODE_SETS[code_set]]
    hri = ""
    index = 2
    while index < len(data):
        byte = data[index]
        if byte == ord("{") and index + 1 < len(data):
            index += 1
            special = data[index]
            if special in _SWITCH:
                code_set = special
                values.append(_SWITCH[special])
            elif special in _FNC:
                values.append(_FNC[special])
                hri += " "
            elif special == ord("4"):  # FNC4 has a different value in code sets A and B
                values.append(101 if code_set == ord("A") else 100)
                hri += " "
            elif special == ord("{") and code_set != ord("C"):
                values.append(ord("{") - 32)
                hri += "{"
            else:
                return None
        elif code_set == ord("C"):
            if byte > 99:
                return None
            values.append(byte)
            hri += f"{byte:02d}"
        elif code_set == ord("A") and byte < 0x60:
            values.append(byte - 32 if byte >= 32 else byte + 64)
            hri += chr(byte) if byte >= 32 else " "
        elif code_set == ord("B") and 32 <= byte < 128:
            values.append(byte - 32)
            hri += chr(byte) if byte != 127 else " "
        else:
            return None
        index += 1
    checksum = (
        values[0] + sum(position * value for position, value in enumerate(values[1:], 1))
    ) % 103
    pattern = "".join(code128.CODES[value] for value in [*values, checksum]) + code128.STOP + "11"
    return _modules(pattern, module_width, hri)
