"""A receipt being printed, and its rendering as a 1-bit PNG plus a text dump.

Printing happens in two shapes, as on a thermal printer in standard mode:
- lines: character cells and bit images collect in a line buffer at the print position, which
  moves as they are added (and with HT, ESC $ and ESC \\). A line feed, or text that wraps,
  prints the line: items sit on a common bottom edge (the baseline) and the paper moves by the
  line spacing, or by the line's height when that is larger;
- blocks: raster images, graphics, barcodes and QR codes are printed on their own, and the
  paper moves by exactly their height.
Lines and blocks are placed in the print area (left margin and print area width), justified
within it in whole dots. Anything beyond the printable width is clipped.
"""

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageChops

type Justification = Literal["left", "center", "right"]
type Boundary = Literal["cut", "connection-closed", "idle-timeout"]


@dataclass(frozen=True, slots=True)
class RenderedReceipt:
    png: bytes
    text: str
    width_dots: int
    height_dots: int
    boundary: Boundary


@dataclass(frozen=True, slots=True)
class PrintArea:
    left: int  # left margin, in dots from the left edge of the printable width
    width: int


class Receipt:
    def __init__(self, width_dots: int) -> None:
        self.width = width_dots
        self._strips: list[tuple[int, Image.Image]] = []  # printed rows: (top, full-width image)
        self._text_lines: list[str] = []
        self._paper_y = 0  # top of the next printed row, in dots
        self._line: list[tuple[int, Image.Image]] = []  # line buffer: (x in the print area, image)
        self._line_text = ""
        self._extent = 0  # the right-most print position reached on this line
        self.position = 0  # print position, in dots from the left edge of the print area

    @property
    def has_content(self) -> bool:
        """Whether anything was printed or waits in the line buffer."""
        return bool(self._strips or self._line)

    @property
    def at_line_start(self) -> bool:
        """The Epson "beginning of the line": nothing buffered and the print position unmoved."""
        return not self._line and self.position == 0

    def add_to_line(self, image: Image.Image, text: str, advance: int | None = None) -> None:
        """Place a character cell or bit image at the print position and move past it."""
        self._line.append((self.position, image))
        self._line_text += text
        self.move_to(self.position + (image.width if advance is None else advance))

    def move_to(self, position: int, text: str = "") -> None:
        """Move the print position without printing; `text` stands for the gap in the text dump."""
        self.position = position
        self._line_text += text
        self._extent = max(self._extent, position)

    def discard_line(self) -> None:
        self._line, self._line_text, self._extent, self.position = [], "", 0, 0

    def print_line(
        self,
        area: PrintArea,
        justification: Justification,
        feed: int,
        text_lines: int = 1,
        upside_down: bool = False,
    ) -> None:
        """Print the line buffer and move the paper by `feed` dots, or the line's height if larger.

        `text_lines` is how many lines the text dump gets: the line's text, then blank lines.
        """
        height = max((image.height for _, image in self._line), default=0)
        if self._line:
            strip = Image.new("1", (self.width, height), 255)
            left = area.left + _left_edge(justification, min(self._extent, area.width), area.width)
            for x, image in self._line:
                # Only ink is pasted: overprinted dots add up, as on a thermal head. Paste clips.
                strip.paste(image, (left + x, height - image.height), ImageChops.invert(image))
            self._strips.append((self._paper_y, strip.rotate(180) if upside_down else strip))
        if text_lines:
            self._text_lines += [self._line_text.rstrip()]
            self._text_lines += [""] * (text_lines - 1)
        self._paper_y += max(feed, height)
        self.discard_line()

    def print_block(
        self, image: Image.Image, area: PrintArea, justification: Justification, text: str
    ) -> None:
        """Print an image, barcode or QR code on its own, with one text dump line."""
        if image.width and image.height:
            strip = Image.new("1", (self.width, image.height), 255)
            left = area.left + _left_edge(justification, min(image.width, area.width), area.width)
            strip.paste(image, (left, 0))
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
