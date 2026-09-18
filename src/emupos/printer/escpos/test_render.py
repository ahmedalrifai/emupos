"""Rendering scenarios of the receipt-printer spec: geometry, images, symbols and code pages."""

import random
import time

import pytest
import segno
import zxingcpp
from PIL import Image, ImageChops, ImageOps

from emupos.events import EventType
from emupos.printer.escpos.glyphs import (
    GLYPH_CODE_PAGES,
    FontName,
    Style,
    cell_image,
    python_codec,
)
from emupos.printer.test_support import Pos, image_of, ink_box

CUT = "1d 56 00"


def render(data: str | bytes, profile: str = "epson-tm-t20iii") -> tuple[Pos, Image.Image]:
    pos = Pos(profile)
    pos.send(data)
    [receipt] = pos.receipts
    return pos, image_of(receipt)


def decode(image: Image.Image) -> list[str]:
    quiet_zone = ImageOps.expand(image.convert("L"), border=40, fill=255)
    return [result.text for result in zxingcpp.read_barcodes(quiet_zone)]


# --- Paper geometry ---------------------------------------------------------------------------


def test_font_a_wraps_at_48_columns() -> None:
    pos, image = render(b"\x1b\x40" + b"A" * 60 + b"\n\x1d\x56\x00", "xprinter-xp80t")

    assert image.width == 576
    assert pos.texts == ["A" * 48 + "\n" + "A" * 12 + "\n"]


def test_font_b_wraps_at_64_columns() -> None:
    pos, _ = render(b"\x1b\x40\x1b\x4d\x01" + b"A" * 70 + b"\n\x1d\x56\x00", "rongta-rp326")

    assert pos.texts == ["A" * 64 + "\n" + "A" * 6 + "\n"]


def test_double_width_halves_the_columns() -> None:
    pos, _ = render(b"\x1b\x40\x1d\x21\x10" + b"A" * 30 + b"\n\x1d\x56\x00")

    assert pos.texts == ["A" * 24 + "\n" + "A" * 6 + "\n"]


def test_centred_text_position_in_dots() -> None:
    _, left = render("1b 40 48 45 4c 4c 4f 0a 1d 56 00")
    _, centred = render("1b 40 1b 61 01 48 45 4c 4c 4f 0a 1d 56 00")

    left_box, centred_box = ink_box(left), ink_box(centred)
    assert left_box is not None
    assert centred_box is not None
    # Left-aligned, the five 12-dot cells are columns 0-59; centred they move by exactly 258.
    assert centred_box[0] - left_box[0] == 258
    assert centred_box[2] - left_box[2] == 258
    assert centred_box[0] >= 258
    assert centred_box[2] <= 318


def test_initialise_resets_character_size() -> None:
    _, image = render("1d 21 11 41 0a 1b 40 41 0a 1d 56 00")

    first, second = ink_box(image.crop((0, 0, 576, 48))), ink_box(image.crop((0, 48, 576, 72)))
    assert image.height == 72  # a 48-dot line, then a 24-dot line
    assert first is not None
    assert second is not None
    assert first[2] <= 24  # inside a 24-dot-wide cell ...
    assert first[2] - first[0] > 12  # ... and wider than a normal one
    assert first[3] - first[1] > 24
    assert second[2] <= 12
    assert second[3] - second[1] <= 24


def test_font_b_cell_is_9_by_17_dots() -> None:
    _, image = render("1b 4d 01 41 41 0a 1d 56 00")

    box = ink_box(image)
    assert image.height == 17
    assert box is not None
    assert 9 < box[2] <= 18  # the second A ends inside the second 9-dot cell


# --- Tabs, spacing, margins and print positions -------------------------------------------


def ink_columns(data: str | bytes) -> tuple[int, int]:
    """Left and right (exclusive) ink columns of a one-line job."""
    _, image = render(data)
    box = ink_box(image)
    assert box is not None
    return box[0], box[2]


B_LEFT, B_RIGHT = ink_columns("42 0a 1d 56 00")  # B's ink inside a cell at column 0


def test_tabs_align_columns() -> None:
    pos, image = render("1b 40 1b 44 0a 00 41 09 42 0a 1d 56 00")

    b = ink_box(image.crop((12, 0, 576, image.height)))
    assert b is not None
    assert (b[0] + 12, b[2] + 12) == (120 + B_LEFT, 120 + B_RIGHT)  # B's cell starts at 120
    assert pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN) == []
    assert pos.texts == ["A         B\n"]  # the tab becomes spaces up to column 10


def test_default_tab_positions_are_every_8_characters() -> None:
    pos, image = render("41 09 42 0a 1d 56 00")

    b = ink_box(image.crop((12, 0, 576, image.height)))
    assert b is not None
    assert b[0] + 12 == 96 + B_LEFT
    assert pos.texts == ["A       B\n"]


def test_tab_positions_count_enlarged_characters_and_spacing() -> None:
    # ESC D 2 while characters are double width with 2 dots of spacing: 2 x (12 + 2) x 2 = 56
    job = "1b 20 02 1d 21 10 1b 44 02 00 1d 21 00 1b 20 00 09 42 0a 1d 56 00"

    assert ink_columns(job) == (56 + B_LEFT, 56 + B_RIGHT)


def test_tab_without_a_further_position_is_ignored() -> None:
    pos, _ = render("1b 44 00 41 09 42 0a 1d 56 00")

    assert pos.texts == ["AB\n"]


def test_tab_past_the_print_area_continues_on_the_next_line() -> None:
    pos, image = render("1d 57 60 00 1b 44 0a 00 41 09 42 0a 1d 56 00")

    assert pos.texts == ["A\nB\n"]
    assert image.height == 30 + 24


def test_right_side_character_spacing() -> None:
    pos, image = render(b"\x1b\x20\x04" + b"A" * 40 + b"\n\x1d\x56\x00")

    assert pos.texts == ["A" * 36 + "\n" + "A" * 4 + "\n"]  # 576 / (12 + 4) = 36 columns
    second = ink_box(image.crop((16, 0, 32, 24)))
    first = ink_box(image.crop((0, 0, 16, 24)))
    assert first == second


def test_left_margin_and_print_area_width() -> None:
    pos, image = render(b"\x1d\x4c\x30\x00\x1d\x57\x60\x00" + b"A" * 10 + b"\n\x1d\x56\x00")

    assert pos.texts == ["A" * 8 + "\nAA\n"]  # 96 dots hold 8 cells
    box = ink_box(image)
    assert box is not None
    assert box[0] >= 48
    assert box[2] <= 48 + 96


def test_justification_uses_the_print_area() -> None:
    left, _ = ink_columns("48 45 4c 4c 4f 0a 1d 56 00")
    centred, _ = ink_columns("1d 4c 30 00 1d 57 60 00 1b 61 01 48 45 4c 4c 4f 0a 1d 56 00")

    assert centred - left == 48 + (96 - 60) // 2


def test_margin_is_ignored_in_the_middle_of_a_line() -> None:
    left, _ = ink_columns("41 1d 4c 30 00 42 0a 1d 56 00")

    assert left < 12


def test_absolute_print_position() -> None:
    pos, image = render("41 1b 24 64 00 42 0a 1d 56 00")

    b = ink_box(image.crop((12, 0, 576, image.height)))
    assert b is not None
    assert b[0] + 12 == 100 + B_LEFT
    assert pos.texts == ["A       B\n"]


def test_absolute_position_beyond_the_print_area_is_ignored() -> None:
    assert ink_columns("1b 24 60 02 42 0a 1d 56 00") == (B_LEFT, B_RIGHT)


def test_relative_print_position() -> None:
    assert ink_columns("1b 5c 10 00 42 0a 1d 56 00") == (16 + B_LEFT, 16 + B_RIGHT)
    assert ink_columns("1b 24 30 00 1b 5c f4 ff 42 0a 1d 56 00") == (36 + B_LEFT, 36 + B_RIGHT)
    # a move to the left of the print area is ignored
    assert ink_columns("1b 5c f4 ff 42 0a 1d 56 00") == (B_LEFT, B_RIGHT)


def test_overprinted_characters_add_their_dots() -> None:
    _, overprinted = render("41 1b 5c f4 ff 42 0a 1d 56 00")  # B printed over A
    _, a = render("41 0a 1d 56 00")

    assert overprinted.histogram()[0] > a.histogram()[0]
    assert ImageChops.logical_and(overprinted, a).tobytes() == overprinted.tobytes()  # A kept


# --- Buffered graphics ------------------------------------------------------------------------


def graphics(
    width: int, height: int, pixels: bytes, scale: int = 1, command: str = "GS ( L"
) -> bytes:
    parameters = bytes([0x30, 0x70, 0x30, scale, scale, 0x31]) + width.to_bytes(2, "little")
    body = parameters + height.to_bytes(2, "little") + pixels
    if command == "GS ( L":
        return bytes.fromhex("1d 28 4c") + len(body).to_bytes(2, "little") + body
    return bytes.fromhex("1d 38 4c") + len(body).to_bytes(4, "little") + body


PRINT_GRAPHICS = bytes.fromhex("1d 28 4c 02 00 30 32")


def test_buffered_graphics_print() -> None:
    pixels = random.Random(5).randbytes(2 * 8)  # noqa: S311 (test data)

    pos, image = render(graphics(16, 8, pixels) + PRINT_GRAPHICS + bytes.fromhex(CUT))

    assert image.size == (576, 8)
    assert image.crop((0, 0, 16, 8)).tobytes("raw", "1;I") == pixels
    assert ink_box(image.crop((16, 0, 576, 8))) is None
    assert pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN) == []
    assert pos.texts == ["[image 16x8]\n"]


def test_gs_8_l_graphics_with_double_scaling_and_odd_width() -> None:
    pixels = bytes([0b10000000, 0b01000000])  # 10 dots wide, 1 row: dots 0 and 9

    pos, image = render(
        graphics(10, 1, pixels, scale=2, command="GS 8 L")
        + b"\x1d\x28\x4c\x02\x00\x30\x02\x1d\x56\x00"
    )

    assert image.height == 2
    assert [x for x in range(24) if image.getpixel((x, 0)) == 0] == [0, 1, 18, 19]
    assert pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN) == []


def test_graphics_follow_justification() -> None:
    _, image = render(
        b"\x1b\x61\x01" + graphics(16, 1, b"\xff\xff") + PRINT_GRAPHICS + bytes.fromhex(CUT)
    )

    assert ink_box(image) == (280, 0, 296, 1)


def test_graphics_wider_than_the_print_area_are_not_printed() -> None:
    pos = Pos()

    pos.send(
        b"\x1d\x57\x08\x00" + graphics(16, 1, b"\xff\xff") + PRINT_GRAPHICS + b"OK\n\x1d\x56\x00"
    )

    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert unknown.data["reason"] == "graphics wider than the print area"
    assert pos.texts == ["O\nK\n"]  # an 8-dot print area still takes one character per line


def test_printing_without_stored_graphics_prints_nothing() -> None:
    pos = Pos()

    pos.send(PRINT_GRAPHICS + b"\x1d\x56\x00")

    assert pos.receipts == []
    assert pos.events == []


def test_multiple_tone_graphics_are_reported() -> None:
    pos = Pos()
    body = bytes([0x30, 0x70, 0x34, 1, 1, 0x31, 16, 0, 1, 0]) + b"\xff\xff"

    pos.send(bytes.fromhex("1d 28 4c") + len(body).to_bytes(2, "little") + body + PRINT_GRAPHICS)

    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert unknown.data["command"] == "GS ( L"


# --- Raster and bit images --------------------------------------------------------------------


def test_full_width_raster_image() -> None:
    data = random.Random(7).randbytes(72 * 32)  # noqa: S311 (test data)

    _, image = render(bytes.fromhex("1d 76 30 00 48 00 20 00") + data + bytes.fromhex(CUT))

    assert image.size == (576, 32)
    assert image.tobytes("raw", "1;I") == data  # 1 bits are black dots
    assert image.getpixel((0, 0)) == (0 if data[0] & 0x80 else 255)  # MSB is the leftmost dot


def test_real_time_byte_values_inside_image_data() -> None:
    pos, image = render("1d 76 30 00 03 00 01 00 10 04 01 1d 56 00")

    assert pos.take() == b""
    row = [image.getpixel((x, 0)) == 0 for x in range(24)]
    expected = [bool(byte >> (7 - bit) & 1) for byte in (0x10, 0x04, 0x01) for bit in range(8)]
    assert row == expected


def test_quadruple_scaling() -> None:
    data = bytes([0b10100000, 0b00000001] * 8)

    _, image = render(bytes.fromhex("1d 76 30 03 02 00 08 00") + data + bytes.fromhex(CUT))

    assert image.height == 16
    for y in range(16):
        for x in range(32):
            source = data[(y // 2) * 2 + (x // 2) // 8] >> (7 - (x // 2) % 8) & 1
            assert (image.getpixel((x, y)) == 0) == bool(source)
    assert ink_box(image) == (0, 0, 32, 16)


def test_image_wider_than_the_paper_is_clipped() -> None:
    _, image = render(bytes.fromhex("1d 76 30 00 50 00 01 00") + b"\xff" * 80 + bytes.fromhex(CUT))

    assert image.size == (576, 1)
    assert image.histogram()[0] == 576


def test_bit_image_columns() -> None:
    _, image = render("1b 2a 00 01 00 80 0a 1d 56 00")

    # Mode 0 at 203 dpi: each column is 2 dots wide (203/2 dpi), each bit 3 dots tall (203/3 dpi).
    assert image.height == 24
    assert ink_box(image) == (0, 0, 2, 3)
    assert image.histogram()[0] == 6


def test_bit_image_24_dot_double_density() -> None:
    _, image = render("1b 2a 21 02 00 80 00 01 ff ff ff 0a 1d 56 00")

    assert image.height == 24
    assert [image.getpixel((0, y)) == 0 for y in (0, 1, 23)] == [True, False, True]
    assert all(image.getpixel((1, y)) == 0 for y in range(24))


# --- Barcodes and QR codes --------------------------------------------------------------------


def test_ean13_module_width_and_height() -> None:
    _, image = render(
        "1d 77 02 1d 68 50 1d 6b 43 0d 34 30 30 36 33 38 31 33 33 33 39 33 31 1d 56 00"
    )

    box = ink_box(image)
    assert box is not None
    assert box[2] - box[0] == 190  # 95 modules x 2 dots
    assert box[3] - box[1] == 80
    assert decode(image) == ["4006381333931"]


def test_barcode_symbologies_decode() -> None:
    cases = {
        # UPC-A bars are EAN-13 bars with a leading 0, which is how zxing reports them
        "UPC-A": (b"\x1d\x6b\x00" + b"03600029145\x00", "0036000291452"),
        "EAN-8": (b"\x1d\x6b\x44\x07" + b"9638507", "96385074"),
        "CODE39": (b"\x1d\x6b\x04" + b"EMUPOS-39\x00", "EMUPOS-39"),
        "ITF": (b"\x1d\x6b\x46\x06" + b"123456", "123456"),
        "CODE128": (b"\x1d\x6b\x49\x0c" + b"{BEMUPOS-128", "EMUPOS-128"),
        "CODE128 set C": (b"\x1d\x6b\x49\x05" + b"{C\x0c\x22\x38", "123456"),
    }
    for name, (command, expected) in cases.items():
        _, image = render(b"\x1d\x68\x40" + command + b"\x1d\x56\x00")
        assert decode(image) == [expected], name


def test_hri_characters_below_the_barcode() -> None:
    _, image = render(
        b"\x1d\x68\x40\x1d\x48\x02\x1d\x6b\x02" + b"4006381333931\x00" + b"\x1d\x56\x00"
    )

    assert image.height == 64 + 24  # bars, then one line of Font A


def test_qr_code_module_size() -> None:
    data = b"https://example.com"
    store = (
        bytes.fromhex("1d 28 6b") + (len(data) + 3).to_bytes(2, "little") + b"\x31\x50\x30" + data
    )

    pos, image = render(
        bytes.fromhex("1d 28 6b 03 00 31 43 04")
        + store
        + bytes.fromhex("1d 28 6b 03 00 31 51 30 1d 56 00")
    )

    modules = len(segno.make_qr(data, error="L", boost_error=False).matrix)
    assert ink_box(image) == (0, 0, modules * 4, modules * 4)
    assert all(image.getpixel((x, 0)) == 0 for x in range(28))  # finder pattern: 7 modules
    assert image.getpixel((28, 0)) == 255
    assert decode(image) == ["https://example.com"]
    assert pos.texts == ["[qr https://example.com]\n"]


def test_unsupported_symbology() -> None:
    pos, image = render("1d 6b 48 05 41 42 43 44 45 4f 4b 0a 1d 56 00")

    [unknown] = pos.events_of(EventType.PRINTER_COMMAND_UNKNOWN)
    assert unknown.data["symbology"] == "CODE93"
    assert pos.texts == ["OK\n"]
    assert image.height == 24


# --- Code page selection ----------------------------------------------------------------------


ALEF = "\N{ARABIC LETTER ALEF ISOLATED FORM}"

# Characters neither bundled font has, so they print the placeholder: the bytes PC720
# maps to C1 controls, the zero-width and direction marks, and WPC1256's Urdu letters in Font B.
FONT_A_GAPS = {0x80, 0x81, 0x84, 0x86, 0x8D, 0x8E, 0x8F, 0x90, 0x200C, 0x200D, 0x200E, 0x200F}
FONT_B_GAPS = (FONT_A_GAPS - {0x200C, 0x200D}) | {
    0x679,
    0x688,
    0x691,
    0x698,
    0x6BA,
    0x6BE,
    0x6C1,
    0x6D2,
}


def cell(character: str | None, font: FontName = "A") -> bytes:
    """The dots of one character cell, or of the placeholder when `character` is None."""
    return cell_image(font, (12, 24) if font == "A" else (9, 17), character, Style()).tobytes()


def cells(image: Image.Image, count: int, font: FontName = "A") -> list[bytes]:
    """The dots of the first `count` character cells of a line."""
    width, height = (12, 24) if font == "A" else (9, 17)
    return [image.crop((i * width, 0, (i + 1) * width, height)).tobytes() for i in range(count)]


def test_arabic_code_page_on_an_epson_profile() -> None:
    pos, image = render("1b 40 1b 74 25 54 4f 54 41 4c c7 0a 1d 56 00")

    assert pos.events_of(EventType.PRINTER_CODEPAGE_UNSUPPORTED) == []
    assert cells(image, 6) == [cell(character) for character in "TOTAL" + ALEF]
    assert ink_box(image.crop((72, 0, 576, 24))) is None
    assert pos.texts == ["TOTAL" + ALEF + "\n"]


def test_latin_and_arabic_stay_in_the_order_received() -> None:
    # "4.75 المجموع", shaped and reversed by the POS, as a printer receives it.
    data = bytes.fromhex("34 2e 37 35 20 df e8 e5 cc e5 e4 c7".replace(" ", ""))
    pos, image = render(b"\x1b\x40\x1b\x74\x25" + data + b"\n\x1d\x56\x00")

    characters = data.decode("cp864")
    assert cells(image, len(data)) == [cell(character) for character in characters]
    assert pos.texts == [characters + "\n"]


def test_same_code_page_under_a_different_number() -> None:
    pos = Pos("rongta-rp326")

    pos.send("1b 74 16 c7 0a 1d 56 00")

    assert pos.events_of(EventType.PRINTER_CODEPAGE_UNSUPPORTED) == []
    assert cells(image_of(pos.receipts[0]), 1) == [cell(ALEF)]


def test_byte_without_a_glyph_in_a_code_page_that_has_a_table() -> None:
    pos, image = render("1b 40 1b 74 25 ff 0a 1d 56 00")  # ff is undefined in PC864

    assert pos.events_of(EventType.PRINTER_CODEPAGE_UNSUPPORTED) == []
    assert cells(image, 1) == [cell(None)]
    assert pos.texts == ["\N{REPLACEMENT CHARACTER}\n"]


def test_number_missing_from_the_profile_map() -> None:
    pos, image = render("1b 74 63 41 c7 0a 1d 56 00")

    [event] = pos.events_of(EventType.PRINTER_CODEPAGE_UNSUPPORTED)
    assert event.data == {"number": 99}
    assert pos.texts == ["A\N{REPLACEMENT CHARACTER}\n"]
    assert cells(image, 2) == [cell("A"), cell(None)]


@pytest.mark.parametrize("code_page", sorted(GLYPH_CODE_PAGES))
def test_every_byte_of_a_listed_code_page_has_a_glyph(code_page: str) -> None:
    codec = python_codec(code_page)
    assert codec is not None
    for byte in range(0x80, 0x100):
        character = bytes([byte]).decode(codec, errors="replace")
        if character == "\N{REPLACEMENT CHARACTER}":
            continue  # a byte this code page leaves undefined
        fonts: list[tuple[FontName, set[int]]] = [("A", FONT_A_GAPS), ("B", FONT_B_GAPS)]
        for font, gaps in fonts:
            drawn = cell(character, font) != cell(None, font)
            assert drawn == (ord(character) not in gaps), f"{code_page} {byte:02x} in font {font}"


def test_default_code_page_has_glyphs() -> None:
    pos, image = render("b0 c4 0a 1d 56 00")

    assert pos.events == []
    assert pos.texts == ["░─\n"]
    assert ink_box(image) is not None


# --- Performance ------------------------------------------------------------------------------


def test_large_raster_job_renders_quickly() -> None:
    data = random.Random(3).randbytes(72 * 2000)  # noqa: S311 (test data)
    job = bytes.fromhex("1d 76 30 00 48 00 d0 07") + data + bytes.fromhex(CUT)
    pos = Pos()

    started = time.perf_counter()
    for offset in range(0, len(job), 4096):  # arrives in network-sized reads
        pos.send(job[offset : offset + 4096])
    elapsed = time.perf_counter() - started

    assert pos.receipts[0].height_dots == 2000
    assert elapsed < 5, f"rendering a 576 x 2000 raster job took {elapsed:.2f} s"
