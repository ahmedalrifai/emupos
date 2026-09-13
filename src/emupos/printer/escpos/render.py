"""A receipt being printed, and its rendering as a 1-bit PNG plus a text dump.

Printing happens in two shapes, as on a thermal printer in standard mode:
- lines: character cells and bit images collect in a line buffer, which is printed by a
  line feed (or when text wraps). Items sit on a common bottom edge (the baseline) and the
  paper moves by the line spacing, or by the line's height when that is larger;
- blocks: raster images, barcodes and QR codes are printed on their own, and the paper moves
  by exactly their height.
Justification positions each line or block within the printable width in whole dots, and
anything beyond the printable width is clipped.
"""

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image

type Justification = Literal["left", "center", "right"]
type Boundary = Literal["cut", "connection-closed", "idle-timeout"]


@dataclass(frozen=True, slots=True)
class RenderedReceipt:
    png: bytes
    text: str
    width_dots: int
    height_dots: int
    boundary: Boundary


class Receipt:
    def __init__(self, width_dots: int) -> None:
        self.width = width_dots
        self._strips: list[tuple[int, Image.Image]] = []  # printed rows: (top, full-width image)
        self._text_lines: list[str] = []
        self._paper_y = 0  # top of the next printed row, in dots
        self._line: list[tuple[Image.Image, str]] = []  # line buffer: (image, dump text)
        self._line_width = 0

    @property
    def has_content(self) -> bool:
        """Whether anything was printed or waits in the line buffer."""
        return bool(self._strips or self._line)

    @property
    def line_is_empty(self) -> bool:
        return not self._line

    def fits_on_line(self, width: int) -> bool:
        return self._line_width + width <= self.width

    def add_to_line(self, image: Image.Image, text: str) -> None:
        """Append a character cell or bit image; the part beyond the printable width is clipped."""
        visible = min(image.width, self.width - self._line_width)
        if visible <= 0:
            return
        if visible < image.width:
            image = image.crop((0, 0, visible, image.height))
        self._line.append((image, text))
        self._line_width += visible

    def discard_line(self) -> None:
        self._line, self._line_width = [], 0

    def print_line(
        self,
        justification: Justification,
        feed: int,
        text_lines: int = 1,
        upside_down: bool = False,
    ) -> None:
        """Print the line buffer and move the paper by `feed` dots, or the line's height if larger.

        `text_lines` is how many lines the text dump gets: the line's text, then blank lines.
        """
        height = max((image.height for image, _ in self._line), default=0)
        if self._line:
            strip = Image.new("1", (self.width, height), 255)
            x = _left_edge(justification, self._line_width, self.width)
            for image, _ in self._line:
                strip.paste(image, (x, height - image.height))
                x += image.width
            self._strips.append((self._paper_y, strip.rotate(180) if upside_down else strip))
        if text_lines:
            self._text_lines += ["".join(text for _, text in self._line).rstrip()]
            self._text_lines += [""] * (text_lines - 1)
        self._paper_y += max(feed, height)
        self.discard_line()

    def print_block(self, image: Image.Image, justification: Justification, text: str) -> None:
        """Print a raster image, barcode or QR code on its own, with one text dump line."""
        image = image.crop((0, 0, min(image.width, self.width), image.height))
        if image.width and image.height:
            strip = Image.new("1", (self.width, image.height), 255)
            strip.paste(image, (_left_edge(justification, image.width, self.width), 0))
            self._strips.append((self._paper_y, strip))
            self._paper_y += image.height
        self._text_lines.append(text)

    def render(self, boundary: Boundary) -> RenderedReceipt | None:
        """The finished receipt, or None when nothing was printed. Trailing feeds are not kept."""
        if not self._strips:
            return None
        height = max(top + strip.height for top, strip in self._strips)
        canvas = Image.new("1", (self.width, height), 255)
        for top, strip in self._strips:
            canvas.paste(strip, (0, top))
        png = io.BytesIO()
        canvas.save(png, format="PNG")
        lines = list(self._text_lines)
        while lines and not lines[-1]:
            lines.pop()
        return RenderedReceipt(
            png.getvalue(), "\n".join(lines) + "\n", self.width, height, boundary
        )


def scale(image: Image.Image, width_factor: int, height_factor: int) -> Image.Image:
    """Enlarge by whole factors; every source dot becomes a width x height block of dots."""
    if (width_factor, height_factor) == (1, 1):
        return image
    size = (image.width * width_factor, image.height * height_factor)
    return image.resize(size, Image.Resampling.NEAREST)  # pyright: ignore[reportUnknownMemberType]


def _left_edge(justification: Justification, width: int, printable_width: int) -> int:
    match justification:
        case "left":
            return 0
        case "center":
            return (printable_width - width) // 2
        case "right":
            return printable_width - width
