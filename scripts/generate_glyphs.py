# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Generate the receipt printer glyph tables from the Spleen bitmap fonts.

    uv run scripts/generate_glyphs.py

Downloads Spleen (BSD-2-Clause, https://github.com/fcambus/spleen), reads its BDF files and
writes the glyph tables in src/emupos/printer/escpos/fonts/. Rerun it to add a code page (extend
CODE_PAGES) or to update Spleen (change VERSION and SHA256).

- Font A (12x24) comes from spleen-12x24. Characters it lacks are downscaled from spleen-16x32.
- Font B (9x17) is spleen-8x16 in the top-left corner of the 9x17 cell.
"""

import hashlib
import io
import tarfile
import urllib.request
from pathlib import Path

VERSION = "2.2.0"
URL = f"https://github.com/fcambus/spleen/releases/download/{VERSION}/spleen-{VERSION}.tar.gz"
SHA256 = "ec42925c6b56d2138c862b2f97147c872e472f674bf03423417d827a08d69a89"
CODE_PAGES = ["cp437"]  # Python codec names of the code pages that get glyphs
OUTPUT = Path(__file__).parent.parent / "src/emupos/printer/escpos/fonts"

type Glyph = list[list[bool]]  # rows of pixels, True = ink


def main() -> None:
    archive = urllib.request.urlopen(URL, timeout=60).read()
    digest = hashlib.sha256(archive).hexdigest()
    if digest != SHA256:
        raise SystemExit(f"unexpected checksum {digest} for {URL}; update SHA256 if intended")
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:

        def read(name: str) -> str:
            member = tar.extractfile(f"spleen-{VERSION}/{name}")
            if member is None:
                raise SystemExit(f"{name} is missing from {URL}")
            return member.read().decode("ascii")

        def bdf(name: str) -> dict[int, Glyph]:
            return parse_bdf(read(name))

        spleen_12x24, spleen_16x32, spleen_8x16 = (
            bdf("spleen-12x24.bdf"),
            bdf("spleen-16x32.bdf"),
            bdf("spleen-8x16.bdf"),
        )
        licence_text = read("LICENSE")

    code_points = sorted(needed_code_points())
    font_a = {cp: spleen_12x24.get(cp) or downscale(spleen_16x32[cp], 12, 24) for cp in code_points}
    font_b = {cp: pad(spleen_8x16[cp], 9, 17) for cp in code_points}
    (OUTPUT / "font-a-12x24.hex").write_text(
        render_table(font_a, "A 12x24", "spleen-12x24 and spleen-16x32", licence_text)
    )
    (OUTPUT / "font-b-9x17.hex").write_text(
        render_table(font_b, "B 9x17", "spleen-8x16", licence_text)
    )
    print(f"wrote {len(code_points)} glyphs per font to {OUTPUT}")


def needed_code_points() -> set[int]:
    points = set(range(0x20, 0x7F))
    for codec in CODE_PAGES:
        points |= {ord(bytes([byte]).decode(codec)) for byte in range(0x80, 0x100)}
    return points


def parse_bdf(text: str) -> dict[int, Glyph]:
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
    return glyphs


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


def render_table(font: dict[int, Glyph], size: str, source: str, licence: str) -> str:
    header = [
        f"# Font {size} glyphs generated by scripts/generate_glyphs.py from {source} (Spleen {VERSION}).",
        "# Each line: code point (hex), then the cell's rows top to bottom as hex. Every row is",
        "# padded to whole bytes, with the most significant bit as the leftmost dot and 1 as ink.",
        "#",
        *(f"# {line}".rstrip() for line in licence.strip().splitlines()),
    ]
    rows = [f"{code_point:04x} {pack(glyph)}" for code_point, glyph in font.items()]
    return "\n".join(header + rows) + "\n"


if __name__ == "__main__":
    main()
