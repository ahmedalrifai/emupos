# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Generate the receipt printer glyph tables from the Spleen and misc-fixed bitmap fonts.

    uv run scripts/generate_glyphs.py

Downloads Spleen (BSD-2-Clause, https://github.com/fcambus/spleen) and the X.Org misc-fixed fonts
(public domain, https://gitlab.freedesktop.org/xorg/font/misc-misc), reads their BDF files and
writes the glyph tables in src/emupos/printer/escpos/fonts/. Rerun it to add a code page (extend
CODE_PAGES, and GLYPH_CODE_PAGES in glyphs.py) or to update a font (change its version and checksum).

Each glyph comes from the first font that has it:

- Font A (12x24): spleen-12x24, else spleen-16x32 downscaled, else misc-fixed 10x20.
- Font B (9x17): spleen-8x16 in the top-left corner of the cell, else misc-fixed 9x15.

A misc-fixed glyph is placed so that its baseline meets Spleen's, and is narrower than Font A's
cell, so the connecting stroke of a joining Arabic letter form is extended to the cell edge; without
that, letters of a word would print 2 dots apart.
"""

import contextlib
import hashlib
import io
import tarfile
import unicodedata
import urllib.request
from pathlib import Path
from typing import NamedTuple

SPLEEN_VERSION = "2.2.0"
SPLEEN_URL = (
    f"https://github.com/fcambus/spleen/releases/download/{SPLEEN_VERSION}"
    f"/spleen-{SPLEEN_VERSION}.tar.gz"
)
SPLEEN_SHA256 = "ec42925c6b56d2138c862b2f97147c872e472f674bf03423417d827a08d69a89"
MISC_VERSION = "1.1.3"
MISC_URL = f"https://www.x.org/releases/individual/font/font-misc-misc-{MISC_VERSION}.tar.xz"
MISC_SHA256 = "79abe361f58bb21ade9f565898e486300ce1cc621d5285bec26e14b6a8618fed"

# Python codec names of the code pages that get glyphs: those the shipped profiles name.
CODE_PAGES = [
    "cp437",
    "cp850",
    "cp852",
    "cp858",
    "cp860",
    "cp863",
    "cp865",
    "cp866",
    "cp1252",
    "cp720",
    "cp864",
    "cp1256",
]
OUTPUT = Path(__file__).parent.parent / "src/emupos/printer/escpos/fonts"

type Glyph = list[list[bool]]  # rows of pixels, True = ink


class Font(NamedTuple):
    """A parsed BDF: its glyphs in the font's own cell, and where that cell's baseline sits."""

    glyphs: dict[int, Glyph]
    baseline: int  # rows from the top of the cell


def main() -> None:
    spleen = archive_files(
        SPLEEN_URL,
        SPLEEN_SHA256,
        f"spleen-{SPLEEN_VERSION}",
        ["spleen-12x24.bdf", "spleen-16x32.bdf", "spleen-8x16.bdf", "LICENSE"],
    )
    misc = archive_files(
        MISC_URL,
        MISC_SHA256,
        f"font-misc-misc-{MISC_VERSION}",
        ["10x20.bdf", "9x15.bdf", "COPYING"],
    )
    spleen_12x24 = parse_bdf(spleen["spleen-12x24.bdf"])
    spleen_16x32 = parse_bdf(spleen["spleen-16x32.bdf"])
    spleen_8x16 = parse_bdf(spleen["spleen-8x16.bdf"])
    misc_10x20 = parse_bdf(misc["10x20.bdf"])
    misc_9x15 = parse_bdf(misc["9x15.bdf"])

    font_a: dict[int, Glyph] = {}
    font_b: dict[int, Glyph] = {}
    for code_point in sorted(needed_code_points()):
        if code_point in spleen_12x24.glyphs:
            font_a[code_point] = spleen_12x24.glyphs[code_point]
        elif code_point in spleen_16x32.glyphs:
            font_a[code_point] = downscale(spleen_16x32.glyphs[code_point], 12, 24)
        elif code_point in misc_10x20.glyphs:
            font_a[code_point] = place(
                misc_10x20.glyphs[code_point], 12, 24, spleen_12x24, misc_10x20, code_point
            )
        if code_point in spleen_8x16.glyphs:
            font_b[code_point] = pad(spleen_8x16.glyphs[code_point], 9, 17)
        elif code_point in misc_9x15.glyphs:
            font_b[code_point] = place(
                misc_9x15.glyphs[code_point], 9, 17, spleen_8x16, misc_9x15, code_point
            )

    licences = [
        (f"Spleen {SPLEEN_VERSION} (https://github.com/fcambus/spleen)", spleen["LICENSE"]),
        (
            f"X.Org font-misc-misc {MISC_VERSION} "
            "(https://gitlab.freedesktop.org/xorg/font/misc-misc)",
            misc["COPYING"],
        ),
    ]
    (OUTPUT / "font-a-12x24.hex").write_text(
        render_table(font_a, "A 12x24", "spleen-12x24, spleen-16x32 and misc-fixed 10x20", licences)
    )
    (OUTPUT / "font-b-9x17.hex").write_text(
        render_table(font_b, "B 9x17", "spleen-8x16 and misc-fixed 9x15", licences)
    )
    needed = len(needed_code_points())
    print(f"wrote {len(font_a)} Font A and {len(font_b)} Font B glyphs of {needed} to {OUTPUT}")
    for name, font in (("A", font_a), ("B", font_b)):
        missing = sorted(needed_code_points() - set(font))
        print(
            f"Font {name} has no glyph for: {', '.join(f'U+{cp:04X}' for cp in missing) or 'none'}"
        )


def archive_files(url: str, sha256: str, prefix: str, names: list[str]) -> dict[str, str]:
    """The named files of a checksummed archive, each under `prefix/`, as text."""
    archive = urllib.request.urlopen(url, timeout=60).read()  # noqa: S310 - the URLs are above
    digest = hashlib.sha256(archive).hexdigest()
    if digest != sha256:
        raise SystemExit(f"unexpected checksum {digest} for {url}; update the checksum if intended")
    files: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for name in names:
            member = tar.extractfile(f"{prefix}/{name}")
            if member is None:
                raise SystemExit(f"{name} is missing from {url}")
            files[name] = member.read().decode("latin-1")
    return files


def needed_code_points() -> set[int]:
    points = set(range(0x20, 0x7F))
    for codec in CODE_PAGES:
        for byte in range(0x80, 0x100):
            with contextlib.suppress(UnicodeDecodeError):  # a byte the code page leaves undefined
                points.add(ord(bytes([byte]).decode(codec)))
    return points


def parse_bdf(text: str) -> Font:
    """Glyphs by code point, each placed in the font's bounding box (the character cell)."""
    lines = iter(text.splitlines())
    cell_width = cell_height = cell_x = cell_y = 0
    glyphs: dict[int, Glyph] = {}
    for line in lines:
        if line.startswith("FONTBOUNDINGBOX"):
            cell_width, cell_height, cell_x, cell_y = map(int, line.split()[1:])
        elif line.startswith("ENCODING"):
            code_point = int(line.split()[1])
            width = height = x = y = 0
            for line in lines:  # the rest of this glyph's header
                if line.startswith("BBX"):
                    width, height, x, y = map(int, line.split()[1:])
                elif line == "BITMAP":
                    break
            glyph = [[False] * cell_width for _ in range(cell_height)]
            top = (cell_height + cell_y) - (height + y)
            for row in range(height):
                hex_row = next(lines)
                bits, row_bits = int(hex_row, 16), len(hex_row) * 4
                for column in range(width):
                    if bits >> (row_bits - 1 - column) & 1:
                        glyph[top + row][x - cell_x + column] = True
            glyphs[code_point] = glyph
    return Font(glyphs, cell_height + cell_y)


def place(
    glyph: Glyph, width: int, height: int, spleen: Font, source: Font, code_point: int
) -> Glyph:
    """A glyph from another font in the cell, on Spleen's baseline, joining strokes reaching out."""
    top, left = spleen.baseline - source.baseline, (width - len(glyph[0])) // 2
    if top < 0 or top + len(glyph) > height or left < 0:
        raise SystemExit(
            f"a {len(glyph[0])}x{len(glyph)} glyph does not fit the {width}x{height} cell"
        )
    rows = [[False] * width for _ in range(height)]
    for row, source_row in enumerate(glyph):
        for column, ink in enumerate(source_row):
            rows[top + row][left + column] = ink
    right = left + len(glyph[0]) - 1
    joins_left, joins_right = joining_sides(code_point)
    for row in rows:  # extend the connecting stroke across the padding, on the side it joins
        if joins_left and row[left]:
            row[:left] = [True] * left
        if joins_right and row[right]:
            row[right + 1 :] = [True] * (width - right - 1)
    return rows


def joining_sides(code_point: int) -> tuple[bool, bool]:
    """Which edges an Arabic letter form connects on: (left, right) of the glyph as drawn.

    A final form joins the letter before it, which sits to its right on paper; an initial form
    joins the letter after it, to its left; a medial form joins both.
    """
    form = unicodedata.decomposition(chr(code_point)).partition(" ")[0]
    return form in ("<initial>", "<medial>"), form in ("<final>", "<medial>")


def downscale(glyph: Glyph, width: int, height: int) -> Glyph:
    """Nearest-neighbour resize; Spleen 16x32 strokes are 2 dots wide, so they survive 3/4."""
    source_height, source_width = len(glyph), len(glyph[0])
    return [
        [
            glyph[row * source_height // height][column * source_width // width]
            for column in range(width)
        ]
        for row in range(height)
    ]


def pad(glyph: Glyph, width: int, height: int) -> Glyph:
    rows = [row + [False] * (width - len(row)) for row in glyph]
    return rows + [[False] * width for _ in range(height - len(rows))]


def pack(glyph: Glyph) -> str:
    """Rows top to bottom, each padded to whole bytes, most significant bit leftmost."""
    row_bytes = (len(glyph[0]) + 7) // 8
    packed = bytearray()
    for row in glyph:
        value = sum(1 << (row_bytes * 8 - 1 - i) for i, ink in enumerate(row) if ink)
        packed += value.to_bytes(row_bytes)
    return packed.hex()


def render_table(
    font: dict[int, Glyph], size: str, source: str, licences: list[tuple[str, str]]
) -> str:
    header = [
        f"# Font {size} glyphs generated by scripts/generate_glyphs.py from {source}.",
        "# Each line: code point (hex), then the cell's rows top to bottom as hex. Every row is",
        "# padded to whole bytes, with the most significant bit as the leftmost dot and 1 as ink.",
    ]
    for name, licence in licences:
        header += [
            "#",
            f"# {name}:",
            *(f"# {line}".rstrip() for line in licence.strip().splitlines()),
        ]
    rows = [f"{code_point:04x} {pack(glyph)}" for code_point, glyph in font.items()]
    return "\n".join(header + rows) + "\n"


if __name__ == "__main__":
    main()
