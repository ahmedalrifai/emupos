"""The print model of one connection: print settings, and the receipt the commands draw.

`PrintModel.process` applies one token. Commands that concern the whole device (status,
Automatic Status Back, drawer kick, cut) are handled by `printer.py` before they get here.
Every command handler cites its page in the Epson ESC/POS Command Reference for TM printers:
https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/<page>.html
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, NamedTuple

from PIL import Image

from emupos.config import PrinterProfile
from emupos.events import Event, EventType
from emupos.printer.escpos.glyphs import (
    GLYPH_CODE_PAGES,
    FontName,
    Style,
    cell_image,
    dump_character,
    glyph_character,
)
from emupos.printer.escpos.render import (
    Boundary,
    Justification,
    Receipt,
    RenderedReceipt,
    scale,
)
from emupos.printer.escpos.symbols import SYMBOLOGIES, THICK_ELEMENT_DOTS, barcode, qr_code
from emupos.printer.escpos.tokenizer import Command, Text, Token, Unknown

# ESC 2 and the power-on line spacing: 3.75 mm, i.e. 30 dots at 203 dpi (TM-T20II Technical
# Reference Guide, "Line spacing ... initial setting").
DEFAULT_LINE_SPACING = 30

# Commands that change nothing on a receipt image: consumed without an event.
IGNORED_COMMANDS = frozenset(
    {
        "CR",  # cr: ignored while auto line feed is off, the default
        "GS b",  # gs_lb: smoothing
        "FS .",  # fs_period: cancel Kanji mode
        "FS &",  # fs_ampersand: select Kanji mode
        "ESC =",  # esc_equal: select peripheral device
        "ESC c 3",  # esc_lc_3: paper sensors for paper-end signals
        "ESC c 4",  # esc_lc_4: paper sensors that stop printing
        "ESC c 5",  # esc_lc_5: panel buttons
        "ESC U",  # esc_cu: unidirectional printing
        "GS P",  # gs_cp: motion units (emupos always works in dots)
        "ESC S",  # esc_cs: select standard mode, the only mode simulated
    }
)


class BitImageMode(NamedTuple):
    dots_per_column: int
    dots_per_bit: int
    bits_per_column: int


# ESC * m (esc_asterisk): density at 203 dpi is 203/2 or 203 dpi across, 203/3 or 203 dpi down.
BIT_IMAGE_MODES = {
    0: BitImageMode(2, 3, 8),
    1: BitImageMode(1, 3, 8),
    32: BitImageMode(2, 1, 24),
    33: BitImageMode(1, 1, 24),
}

# GS v 0 m (gs_lv_0): (width factor, height factor) for m = 0-3 and 48-51.
RASTER_SCALES = {0: (1, 1), 1: (2, 1), 2: (1, 2), 3: (2, 2)}


@dataclass(slots=True)
class Settings:
    """The print settings of one connection; ESC @ restores these defaults."""

    code_page: int
    font: FontName = "A"
    width: int = 1
    height: int = 1
    emphasized: bool = False
    underline: int = 0
    reverse: bool = False
    upside_down: bool = False
    justification: Justification = "left"
    line_spacing: int = DEFAULT_LINE_SPACING
    barcode_module_width: int = 3  # gs_lw default
    barcode_height: int = 162  # gs_lh default
    hri_position: int = 0  # gs_ch: 0 none, 1 above, 2 below, 3 both
    hri_font: FontName = "A"
    qr_module_size: int = 3  # gs_lparen_lk_fn167 default
    qr_error_correction: str = "L"  # gs_lparen_lk_fn169 default
    qr_data: bytes = b""  # gs_lparen_lk_fn180 symbol storage area

    @property
    def style(self) -> Style:
        return Style(self.width, self.height, self.emphasized, self.underline, self.reverse)


def unknown_command_event(device_id: str, raw: bytes, **details: object) -> Event:
    return Event(EventType.PRINTER_COMMAND_UNKNOWN, device_id, {"bytes": raw.hex(" "), **details})


class PrintModel:
    def __init__(self, device_id: str, profile: PrinterProfile) -> None:
        self._device_id = device_id
        self._profile = profile
        self._events: list[Event] = []
        self.settings = Settings(code_page=profile.default_code_page)
        self.receipt = Receipt(profile.width_dots)

    def process(self, token: Token) -> list[Event]:
        match token:
            case Text():
                self._print_text(token.data)
            case Unknown():
                self._events.append(unknown_command_event(self._device_id, token.raw))
            case Command(name=name) if name in self._HANDLERS:
                self._HANDLERS[name](self, token)
            case Command(name=name) if name in IGNORED_COMMANDS:
                pass
            case Command():
                self._unknown(token)
        events, self._events = self._events, []
        return events

    def finish(self, boundary: Boundary) -> RenderedReceipt | None:
        """End the job: print the line buffer and return the receipt, if anything was printed."""
        if not self.receipt.line_is_empty:
            self._print_line(self.settings.line_spacing)
        receipt = self.receipt.render(boundary)
        self.receipt = Receipt(self._profile.width_dots)
        return receipt

    # --- text and paper feed ---------------------------------------------------------------

    def _print_text(self, data: bytes) -> None:
        settings = self.settings
        font = self._profile.font_a if settings.font == "A" else self._profile.font_b
        code_page = self._profile.code_pages.get(settings.code_page)
        for byte in data:
            character = glyph_character(byte, code_page)
            image = cell_image(settings.font, (font.width, font.height), character, settings.style)
            if not self.receipt.fits_on_line(image.width) and not self.receipt.line_is_empty:
                self._print_line(settings.line_spacing)  # wrap: the character starts the next line
            self.receipt.add_to_line(image, dump_character(byte, code_page))

    def _print_line(self, feed: int, text_lines: int = 1) -> None:
        settings = self.settings
        self.receipt.print_line(settings.justification, feed, text_lines, settings.upside_down)

    def _line_feed(self, _command: Command) -> None:  # lf
        self._print_line(self.settings.line_spacing)

    def _print_and_feed_lines(self, command: Command) -> None:  # esc_ld
        lines = command.params[0]
        self._print_line(lines * self.settings.line_spacing, text_lines=max(lines, 1))

    def _print_and_feed_dots(self, command: Command) -> None:  # esc_cj
        self._print_line(command.params[0], text_lines=0 if self.receipt.line_is_empty else 1)

    def _select_default_line_spacing(self, _command: Command) -> None:  # esc_2
        self.settings.line_spacing = DEFAULT_LINE_SPACING

    def _set_line_spacing(self, command: Command) -> None:  # esc_3
        self.settings.line_spacing = command.params[0]

    # --- print settings --------------------------------------------------------------------

    def _initialize(self, _command: Command) -> None:  # esc_atsign: clears the line buffer too
        self.settings = Settings(code_page=self._profile.default_code_page)
        self.receipt.discard_line()

    def _select_print_mode(self, command: Command) -> None:  # esc_exclamation
        n = command.params[0]
        self.settings.font = "B" if n & 0x01 else "A"
        self.settings.emphasized = bool(n & 0x08)
        self.settings.height = 2 if n & 0x10 else 1
        self.settings.width = 2 if n & 0x20 else 1
        self.settings.underline = 1 if n & 0x80 else 0

    def _emphasis(self, command: Command) -> None:  # esc_ce, esc_cg (double-strike looks the same)
        self.settings.emphasized = bool(command.params[0] & 0x01)

    def _underline(self, command: Command) -> None:  # esc_minus: 0-2 or 48-50, thickness in dots
        n = command.params[0]
        if n in (0, 1, 2, 48, 49, 50):
            self.settings.underline = n % 48

    def _select_font(self, command: Command) -> None:  # esc_cm
        match command.params[0]:
            case 0 | 48:
                self.settings.font = "A"
            case 1 | 49:
                self.settings.font = "B"
            case _:
                self._unknown(command)

    def _character_size(self, command: Command) -> None:  # gs_exclamation
        n = command.params[0]
        self.settings.width = (n >> 4 & 0x07) + 1
        self.settings.height = (n & 0x07) + 1

    def _justification(self, command: Command) -> None:  # esc_la: only at the start of a line
        n = command.params[0]
        if n in (0, 1, 2, 48, 49, 50) and self.receipt.line_is_empty:
            self.settings.justification = ("left", "center", "right")[n % 48]

    def _upside_down(self, command: Command) -> None:  # esc_lbrace: only at the start of a line
        if self.receipt.line_is_empty:
            self.settings.upside_down = bool(command.params[0] & 0x01)

    def _reverse(self, command: Command) -> None:  # gs_cb
        self.settings.reverse = bool(command.params[0] & 0x01)

    def _select_code_page(self, command: Command) -> None:  # esc_lt, numbers from the profile
        number = command.params[0]
        self.settings.code_page = number
        name = self._profile.code_pages.get(number)
        if name not in GLYPH_CODE_PAGES:
            data: dict[str, object] = {"number": number}
            if name is not None:
                data["code_page"] = name
            self._events.append(
                Event(EventType.PRINTER_CODEPAGE_UNSUPPORTED, self._device_id, data)
            )

    # --- images ----------------------------------------------------------------------------

    def _bit_image(self, command: Command) -> None:  # esc_asterisk: columns, MSB is the top dot
        m, columns = command.params[0], command.params[1] + command.params[2] * 256
        mode = BIT_IMAGE_MODES.get(m)
        if mode is None:
            self._unknown(command)
            return
        if columns == 0:
            return
        # Each column is a row of bits here; transposing turns rows into columns.
        image = Image.frombytes("1", (mode.bits_per_column, columns), command.data, "raw", "1;I")
        image = image.transpose(Image.Transpose.TRANSPOSE)
        image = scale(image, mode.dots_per_column, mode.dots_per_bit)
        self.receipt.add_to_line(image, f"[image {image.width}x{image.height}]")

    def _raster_image(self, command: Command) -> None:  # gs_lv_0: rows, MSB is the leftmost dot
        m, params = command.params[0], command.params
        width, height = (params[1] + params[2] * 256) * 8, params[3] + params[4] * 256
        factors = RASTER_SCALES.get(m % 48 if m >= 48 else m)
        if factors is None:
            self._unknown(command)
            return
        if width and height:
            image = Image.frombytes("1", (width, height), command.data, "raw", "1;I")
            image = scale(image, *factors)
            self._print_block(image, f"[image {image.width}x{image.height}]")

    # --- barcodes and QR codes -------------------------------------------------------------

    def _barcode(self, command: Command) -> None:  # gs_lk
        m = command.params[0]
        data = command.data[:-1] if m <= 6 else command.data[1:]  # drop NUL (A) or length n (B)
        symbology = SYMBOLOGIES.get(m)
        settings = self.settings
        bars = barcode(symbology, data, settings.barcode_module_width) if symbology else None
        if bars is None:
            self._unknown(command, **({"symbology": symbology} if symbology else {}))
            return
        image = _with_hri(
            bars.image(settings.barcode_height), self._hri_image(bars.hri), settings.hri_position
        )
        self._print_block(image, f"[barcode {symbology} {bars.hri}]")

    def _module_width(self, command: Command) -> None:  # gs_lw
        if command.params[0] in THICK_ELEMENT_DOTS:
            self.settings.barcode_module_width = command.params[0]

    def _barcode_height(self, command: Command) -> None:  # gs_lh
        if command.params[0] >= 1:
            self.settings.barcode_height = command.params[0]

    def _hri_position(self, command: Command) -> None:  # gs_ch
        if command.params[0] in (0, 1, 2, 3, 48, 49, 50, 51):
            self.settings.hri_position = command.params[0] % 48

    def _hri_font(self, command: Command) -> None:  # gs_lf
        if command.params[0] in (0, 1, 48, 49):
            self.settings.hri_font = "A" if command.params[0] % 48 == 0 else "B"

    def _two_dimensional_code(self, command: Command) -> None:  # gs_lparen_lk: cn fn [arguments]
        data = command.data
        cn, fn = (data[0], data[1]) if len(data) >= 2 else (None, None)
        argument = data[2] if len(data) >= 3 else None
        if cn != 49:  # only QR codes (cn = 49); PDF417 (48) and the others are not simulated
            self._unknown(command)
            return
        settings = self.settings
        match fn:
            case 65:  # fn 165, select the model: printed as model 2 whatever is selected
                pass
            case 67 if argument is not None and 1 <= argument <= 16:  # fn 167, module size
                settings.qr_module_size = argument
            case 69 if argument is not None and 48 <= argument <= 51:  # fn 169, error correction
                settings.qr_error_correction = "LMQH"[argument - 48]
            case 80 if argument == 48:  # fn 180, store the data
                settings.qr_data = data[3:]
            case 81 if argument == 48:  # fn 181, print the stored data
                self._print_qr_code(command)
            case _:
                self._unknown(command)

    def _print_qr_code(self, command: Command) -> None:
        settings = self.settings
        if not settings.qr_data:
            return
        image = qr_code(settings.qr_data, settings.qr_error_correction, settings.qr_module_size)
        if image is None:
            self._unknown(command, reason="too much data for a QR code")
            return
        self._print_block(image, f"[qr {settings.qr_data.decode('utf-8', errors='replace')}]")

    # --- helpers ---------------------------------------------------------------------------

    def _print_block(self, image: Image.Image, text: str) -> None:
        if not self.receipt.line_is_empty:
            self._print_line(self.settings.line_spacing)
        self.receipt.print_block(image, self.settings.justification, text)

    def _hri_image(self, text: str) -> Image.Image:
        font = self.settings.hri_font
        cell = self._profile.font_a if font == "A" else self._profile.font_b
        image = Image.new("1", (cell.width * len(text), cell.height), 255)
        for index, character in enumerate(text):
            cell_size = (cell.width, cell.height)
            image.paste(cell_image(font, cell_size, character, Style()), (index * cell.width, 0))
        return image

    def _unknown(self, command: Command, **details: object) -> None:
        self._events.append(
            unknown_command_event(self._device_id, command.raw, command=command.name, **details)
        )

    # Command name -> handler. Adding a print command: write its handler above, add one line here.
    _HANDLERS: ClassVar[dict[str, Callable[["PrintModel", Command], None]]] = {
        "LF": _line_feed,
        "ESC d": _print_and_feed_lines,
        "ESC J": _print_and_feed_dots,
        "ESC 2": _select_default_line_spacing,
        "ESC 3": _set_line_spacing,
        "ESC @": _initialize,
        "ESC !": _select_print_mode,
        "ESC E": _emphasis,
        "ESC G": _emphasis,
        "ESC -": _underline,
        "ESC M": _select_font,
        "GS !": _character_size,
        "ESC a": _justification,
        "ESC {": _upside_down,
        "GS B": _reverse,
        "ESC t": _select_code_page,
        "ESC *": _bit_image,
        "GS v 0": _raster_image,
        "GS k": _barcode,
        "GS w": _module_width,
        "GS h": _barcode_height,
        "GS H": _hri_position,
        "GS f": _hri_font,
        "GS ( k": _two_dimensional_code,
    }


def _with_hri(bars: Image.Image, hri: Image.Image, position: int) -> Image.Image:
    """Stack HRI characters above (1), below (2) or on both sides (3) of the bars, centred."""
    above, below = position in (1, 3), position in (2, 3)
    parts = [hri] * above + [bars] + [hri] * below
    width = max(part.width for part in parts)
    image = Image.new("1", (width, sum(part.height for part in parts)), 255)
    top = 0
    for part in parts:
        image.paste(part, ((width - part.width) // 2, top))
        top += part.height
    return image
