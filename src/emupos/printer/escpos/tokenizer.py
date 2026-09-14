"""Incremental ESC/POS tokenizer: turns the bytes of one connection into commands.

Every recognised command is one entry in `COMMANDS`: its prefix bytes, how many parameter
bytes follow, and how long its variable data is. Adding a command is adding one entry.
The tokenizer only knows the syntax; what a command does lives in `model.py` and
`printer.py`.

Rules (receipt-printer spec, "Incremental ESC/POS decoding"):
- A command split across reads waits for its remaining bytes, so any split of a stream gives
  the same tokens as the whole stream, except that a run of text may arrive as several `Text`
  tokens.
- Bytes inside a command's parameters or data belong to that command, so a real-time command
  (e.g. DLE EOT) is only recognised where a new command starts.
- A prefix followed by a byte that forms no known command is skipped as two `Unknown` bytes;
  any other control byte is skipped alone.

References are pages of the Epson ESC/POS Command Reference for TM printers:
https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/<page>.html
"""

from collections.abc import Callable
from dataclasses import dataclass

# The number of data bytes a command has, given its parameter bytes and the stream with the
# index where the data starts; None when more bytes must arrive before it can be known.
type DataLength = Callable[[bytes, bytes, int], int | None]


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    params: int = 0
    data: DataLength | None = None
    realtime: bool = False


@dataclass(frozen=True, slots=True)
class Text:
    """Printable bytes (0x20-0xff), printed with the current code page."""

    data: bytes


@dataclass(frozen=True, slots=True)
class Command:
    name: str  # as in the Epson reference, e.g. "GS v 0"
    raw: bytes  # every byte of the command, prefix included
    params: bytes
    data: bytes
    realtime: bool


@dataclass(frozen=True, slots=True)
class Unknown:
    """Skipped bytes: no recognised command, or a command cut off when the connection closed."""

    raw: bytes


type Token = Text | Command | Unknown


def _nul_terminated(_params: bytes, stream: bytes, start: int) -> int | None:
    end = stream.find(0, start)
    return None if end < 0 else end - start + 1


def _tab_positions_length(_params: bytes, stream: bytes, start: int) -> int | None:
    """ESC D n1...nk NUL: ends at NUL, before a value not above the previous one, or after 32."""
    previous = 0
    for index, value in enumerate(stream[start:]):
        if value == 0:
            return index + 1
        if value <= previous or index == 32:
            return index  # the following bytes are normal data
        previous = value
    return None


def _length_in_params(offset: int) -> DataLength:
    """Data length is a little-endian 16-bit number (pL pH) at `offset` in the parameters."""
    return lambda params, _stream, _start: params[offset] + params[offset + 1] * 256


def _bit_image_length(params: bytes, _stream: bytes, _start: int) -> int:
    m, columns = params[0], params[1] + params[2] * 256
    return columns * (3 if m in (32, 33) else 1)  # 24-dot modes send 3 bytes per column


def _raster_length(params: bytes, _stream: bytes, _start: int) -> int:
    return (params[1] + params[2] * 256) * (params[3] + params[4] * 256)


def _barcode_length(params: bytes, stream: bytes, start: int) -> int | None:
    m = params[0]
    if m <= 6:  # Function A: data ends with NUL
        return _nul_terminated(params, stream, start)
    if 65 <= m <= 79:  # Function B: n, then n bytes
        return None if start >= len(stream) else 1 + stream[start]
    return 0


def _graphics_length(params: bytes, _stream: bytes, _start: int) -> int:
    return int.from_bytes(params, "little")


def _cut_length(params: bytes, _stream: bytes, _start: int) -> int:
    return 1 if params[0] in (65, 66, 97, 98, 103, 104) else 0  # feed-and-cut forms take n


def _dle_eot_length(params: bytes, _stream: bytes, _start: int) -> int:
    return 1 if params[0] in (7, 8, 18) else 0  # these status requests take a second byte a


def _dle_dc4_length(params: bytes, _stream: bytes, _start: int) -> int:
    # fn 1 pulse (m t), fn 2 power-off (a b), fn 3 buzzer (a n r t1 t2), fn 7 status (m),
    # fn 8 clear buffer (d1-d7): dle_dc4_fn1, dle_dc4_fn2, dle_dc4_fn3, dle_dc4_fn7, dle_dc4_fn8
    return {1: 2, 2: 2, 3: 5, 7: 1, 8: 7}.get(params[0], 0)


# fmt: off
COMMANDS: dict[bytes, CommandSpec] = {
    # Real-time commands
    b"\x10\x04": CommandSpec("DLE EOT", 1, _dle_eot_length, realtime=True),  # dle_eot
    b"\x10\x05": CommandSpec("DLE ENQ", 1, realtime=True),                   # dle_enq
    b"\x10\x14": CommandSpec("DLE DC4", 1, _dle_dc4_length, realtime=True),  # dle_dc4_fn1
    # Print and paper feed
    b"\x0a": CommandSpec("LF"),                                   # lf
    b"\x09": CommandSpec("HT"),                                   # ht
    b"\x0d": CommandSpec("CR"),                                   # cr
    b"\x1b\x64": CommandSpec("ESC d", 1),                         # esc_ld
    b"\x1b\x4a": CommandSpec("ESC J", 1),                         # esc_cj
    b"\x1b\x32": CommandSpec("ESC 2"),                            # esc_2
    b"\x1b\x33": CommandSpec("ESC 3", 1),                         # esc_3
    # Printer settings
    b"\x1b\x40": CommandSpec("ESC @"),                            # esc_atsign
    b"\x1b\x21": CommandSpec("ESC !", 1),                         # esc_exclamation
    b"\x1b\x45": CommandSpec("ESC E", 1),                         # esc_ce
    b"\x1b\x47": CommandSpec("ESC G", 1),                         # esc_cg
    b"\x1b\x2d": CommandSpec("ESC -", 1),                         # esc_minus
    b"\x1b\x4d": CommandSpec("ESC M", 1),                         # esc_cm
    b"\x1d\x21": CommandSpec("GS !", 1),                          # gs_exclamation
    b"\x1b\x61": CommandSpec("ESC a", 1),                         # esc_la
    b"\x1b\x7b": CommandSpec("ESC {", 1),                         # esc_lbrace
    b"\x1d\x42": CommandSpec("GS B", 1),                          # gs_cb
    b"\x1d\x62": CommandSpec("GS b", 1),                          # gs_lb
    b"\x1b\x74": CommandSpec("ESC t", 1),                         # esc_lt
    b"\x1b\x52": CommandSpec("ESC R", 1),                         # esc_cr
    b"\x1b\x20": CommandSpec("ESC SP", 1),                        # esc_space
    b"\x1b\x24": CommandSpec("ESC $", 2),                         # esc_dollarssign
    b"\x1b\x5c": CommandSpec("ESC \\", 2),                        # esc_backslash
    b"\x1b\x44": CommandSpec("ESC D", 0, _tab_positions_length),  # esc_cd
    b"\x1b\x55": CommandSpec("ESC U", 1),                         # esc_cu
    b"\x1b\x56": CommandSpec("ESC V", 1),                         # esc_cv
    b"\x1b\x3d": CommandSpec("ESC =", 1),                         # esc_equal
    b"\x1b\x63\x30": CommandSpec("ESC c 0", 1),                   # esc_lc_0
    b"\x1b\x63\x31": CommandSpec("ESC c 1", 1),                   # esc_lc_1
    b"\x1b\x63\x33": CommandSpec("ESC c 3", 1),                   # esc_lc_3
    b"\x1b\x63\x34": CommandSpec("ESC c 4", 1),                   # esc_lc_4
    b"\x1b\x63\x35": CommandSpec("ESC c 5", 1),                   # esc_lc_5
    b"\x1d\x4c": CommandSpec("GS L", 2),                          # gs_cl
    b"\x1d\x57": CommandSpec("GS W", 2),                          # gs_cw
    b"\x1d\x50": CommandSpec("GS P", 2),                          # gs_cp
    b"\x1c\x2e": CommandSpec("FS ."),                             # fs_period
    b"\x1c\x26": CommandSpec("FS &"),                             # fs_ampersand
    b"\x1b\x28": CommandSpec("ESC (", 3, _length_in_params(1)),   # esc_lparen_ca (fn, pL, pH)
    b"\x1c\x28": CommandSpec("FS (", 3, _length_in_params(1)),    # fs_lparen_ca (fn, pL, pH)
    # Page mode (not simulated)
    b"\x1b\x4c": CommandSpec("ESC L"),                            # esc_cl
    b"\x1b\x53": CommandSpec("ESC S"),                            # esc_cs
    # Paper cut, drawer and status
    b"\x1d\x56": CommandSpec("GS V", 1, _cut_length),             # gs_cv
    b"\x1b\x70": CommandSpec("ESC p", 3),                         # esc_lp
    b"\x1d\x72": CommandSpec("GS r", 1),                          # gs_lr
    b"\x1d\x61": CommandSpec("GS a", 1),                          # gs_la
    # Images
    b"\x1b\x2a": CommandSpec("ESC *", 3, _bit_image_length),      # esc_asterisk
    b"\x1d\x76\x30": CommandSpec("GS v 0", 5, _raster_length),    # gs_lv_0
    b"\x1d\x28": CommandSpec("GS (", 3, _length_in_params(1)),    # gs_lparen_ce etc. (fn, pL, pH)
    b"\x1d\x28\x4c": CommandSpec("GS ( L", 2, _length_in_params(0)),  # gs_lparen_cl (pL, pH)
    b"\x1d\x38\x4c": CommandSpec("GS 8 L", 4, _graphics_length),     # gs_lparen_cl (p1-p4)
    # Barcodes and two-dimensional codes
    b"\x1d\x6b": CommandSpec("GS k", 1, _barcode_length),         # gs_lk
    b"\x1d\x77": CommandSpec("GS w", 1),                          # gs_lw
    b"\x1d\x68": CommandSpec("GS h", 1),                          # gs_lh
    b"\x1d\x48": CommandSpec("GS H", 1),                          # gs_ch
    b"\x1d\x66": CommandSpec("GS f", 1),                          # gs_lf
    b"\x1d\x28\x6b": CommandSpec("GS ( k", 2, _length_in_params(0)),  # gs_lparen_lk (pL, pH)
}
# fmt: on

_LONGEST_PREFIX = max(len(prefix) for prefix in COMMANDS)


@dataclass(frozen=True, slots=True)
class _Incomplete:
    needed: int  # the command needs at least this many bytes, counted from its first byte


class Tokenizer:
    """Tokenizes one connection's byte stream; keeps an incomplete command between reads."""

    def __init__(self) -> None:
        self._pending = bytearray()
        self._needed = 0

    def feed(self, data: bytes) -> list[Token]:
        self._pending += data
        if len(self._pending) < self._needed:
            return []  # still receiving a long command, such as an image
        stream = bytes(self._pending)
        tokens: list[Token] = []
        position, self._needed = 0, 0
        while position < len(stream):
            token = _next_token(stream, position)
            if isinstance(token, _Incomplete):
                self._needed = token.needed
                break
            tokens.append(token)
            position += len(token.data) if isinstance(token, Text) else len(token.raw)
        del self._pending[:position]
        return tokens

    def close(self) -> Unknown | None:
        """The connection closed: an incomplete command still pending is returned as Unknown."""
        if not self._pending:
            return None
        unknown = Unknown(bytes(self._pending))
        self._pending.clear()
        self._needed = 0
        return unknown


def _next_token(stream: bytes, start: int) -> Token | _Incomplete:
    if stream[start] >= 0x20:
        end = start
        while end < len(stream) and stream[end] >= 0x20:
            end += 1
        return Text(stream[start:end])

    available = stream[start : start + _LONGEST_PREFIX]
    if any(len(prefix) > len(available) and prefix.startswith(available) for prefix in COMMANDS):
        return _Incomplete(len(available) + 1)  # a longer prefix may still match
    for size in range(len(available), 0, -1):
        spec = COMMANDS.get(available[:size])
        if spec is not None:
            return _command(spec, stream, start, size)
    if available[0] in (0x10, 0x1B, 0x1C, 0x1D) and len(available) >= 2:
        return Unknown(available[:2])
    return Unknown(available[:1])


def _command(
    spec: CommandSpec, stream: bytes, start: int, prefix_size: int
) -> Command | _Incomplete:
    data_start = start + prefix_size + spec.params
    if data_start > len(stream):
        return _Incomplete(data_start - start)
    params = stream[start + prefix_size : data_start]
    data_size = 0 if spec.data is None else spec.data(params, stream, data_start)
    if data_size is None:
        return _Incomplete(len(stream) - start + 1)
    end = data_start + data_size
    if end > len(stream):
        return _Incomplete(end - start)
    return Command(spec.name, stream[start:end], params, stream[data_start:end], spec.realtime)
