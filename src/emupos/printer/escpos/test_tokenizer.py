from itertools import pairwise

from hypothesis import given
from hypothesis import strategies as st

from emupos.printer.escpos.tokenizer import Command, Text, Token, Tokenizer, Unknown


def tokens_of(*reads: bytes) -> list[Token]:
    tokenizer = Tokenizer()
    tokens = [token for data in reads for token in tokenizer.feed(data)]
    if (pending := tokenizer.close()) is not None:
        tokens.append(pending)
    return _merge_text(tokens)


def _merge_text(tokens: list[Token]) -> list[Token]:
    merged: list[Token] = []
    for token in tokens:
        if isinstance(token, Text) and merged and isinstance(merged[-1], Text):
            merged[-1] = Text(merged[-1].data + token.data)
        else:
            merged.append(token)
    return merged


def names(tokens: list[Token]) -> list[str]:
    def name(token: Token) -> str:
        match token:
            case Command():
                return token.name
            case Unknown():
                return f"Unknown:{token.raw.hex(' ')}"
            case Text():
                return f"Text:{token.data.decode('latin-1')}"

    return [name(token) for token in tokens]


def test_command_split_across_reads_waits_for_the_rest() -> None:
    assert tokens_of(bytes.fromhex("48 69 0a 1d"), bytes.fromhex("56 00")) == tokens_of(
        bytes.fromhex("48 69 0a 1d 56 00")
    )
    assert names(tokens_of(bytes.fromhex("48 69 0a 1d 56 00"))) == ["Text:Hi", "LF", "GS V"]


def test_unknown_escape_sequence_is_skipped_as_two_bytes() -> None:
    tokens = tokens_of(bytes.fromhex("1b 40 1b fe 48 69 0a"))

    assert names(tokens) == ["ESC @", "Unknown:1b fe", "Text:Hi", "LF"]


def test_lone_control_byte_is_skipped_alone() -> None:
    assert names(tokens_of(bytes.fromhex("00 41"))) == ["Unknown:00", "Text:A"]


def test_incomplete_command_at_close_is_returned_as_unknown() -> None:
    tokens = tokens_of(bytes.fromhex("48 69 0a 1d 76 30 00"))

    assert names(tokens) == ["Text:Hi", "LF", "Unknown:1d 76 30 00"]


def test_realtime_bytes_inside_raster_data_belong_to_the_image() -> None:
    image = bytes.fromhex("1d 76 30 00 03 00 01 00 10 04 01")

    tokens = tokens_of(image + bytes.fromhex("10 04 01"))

    assert names(tokens) == ["GS v 0", "DLE EOT"]
    assert tokens[0] == Command("GS v 0", image, image[3:8], bytes.fromhex("10 04 01"), False)


def test_realtime_command_inside_text() -> None:
    tokens = tokens_of(bytes.fromhex("48 65 10 04 01 6c 6c 6f 0a"))

    assert names(tokens) == ["Text:He", "DLE EOT", "Text:llo", "LF"]


def test_barcode_function_a_ends_at_nul_and_function_b_is_length_prefixed() -> None:
    a = bytes.fromhex("1d 6b 02") + b"4006381333931\x00"
    b = bytes.fromhex("1d 6b 49 0c") + b"{BEMUPOS-128"

    tokens = tokens_of(a + b)

    assert [t.data for t in tokens if isinstance(t, Command)] == [
        b"4006381333931\x00",
        b"\x0c{BEMUPOS-128",
    ]


def test_declared_lengths_consume_pdf417_and_nv_graphics_in_full() -> None:
    pdf417 = bytes.fromhex("1d 28 6b 03 00 30 41 00")
    nv_graphics = bytes.fromhex("1d 28 4c 06 00 30 45 20 20 01 01")
    nv_graphics_long = bytes.fromhex("1d 38 4c 02 00 00 00 30 32")

    tokens = tokens_of(pdf417 + nv_graphics + nv_graphics_long + b"OK")

    assert [t.raw for t in tokens if isinstance(t, Command)] == [
        pdf417,
        nv_graphics,
        nv_graphics_long,
    ]
    assert names(tokens) == ["GS ( k", "GS ( L", "GS 8 L", "Text:OK"]


def test_bit_image_24_dot_mode_reads_three_bytes_per_column() -> None:
    tokens = tokens_of(bytes.fromhex("1b 2a 21 02 00 01 02 03 04 05 06 41"))

    assert names(tokens) == ["ESC *", "Text:A"]


def test_tab_positions_end_at_nul() -> None:
    assert names(tokens_of(bytes.fromhex("1b 44 08 10 00 41"))) == ["ESC D", "Text:A"]


def test_tab_positions_end_before_a_value_that_does_not_ascend() -> None:
    tokens = tokens_of(bytes.fromhex("1b 44 08 10 04 41"))

    assert names(tokens) == ["ESC D", "Unknown:04", "Text:A"]
    assert tokens[0] == Command("ESC D", bytes.fromhex("1b 44 08 10"), b"", b"\x08\x10", False)


def test_tab_positions_end_after_32_values() -> None:
    tokens = tokens_of(bytes.fromhex("1b 44") + bytes(range(1, 34)) + b"\x00")

    assert names(tokens)[:2] == ["ESC D", "Text:!"]  # value 33 (0x21) is printed as text
    assert tokens[0] == Command(
        "ESC D", bytes.fromhex("1b 44") + bytes(range(1, 33)), b"", bytes(range(1, 33)), False
    )


def test_feed_and_cut_takes_an_extra_byte() -> None:
    assert names(tokens_of(bytes.fromhex("1d 56 41 10 41"))) == ["GS V", "Text:A"]
    assert names(tokens_of(bytes.fromhex("1d 56 00 41"))) == ["GS V", "Text:A"]


def test_status_requests_with_a_second_parameter() -> None:
    assert names(tokens_of(bytes.fromhex("10 04 12 01 41"))) == ["DLE EOT", "Text:A"]
    assert names(tokens_of(bytes.fromhex("10 14 01 00 01 41"))) == ["DLE DC4", "Text:A"]
    assert names(tokens_of(bytes.fromhex("10 14 03 01 02 03 04 05 41"))) == ["DLE DC4", "Text:A"]
    assert names(tokens_of(bytes.fromhex("10 14 08 01 03 14 01 06 02 08 41"))) == [
        "DLE DC4",
        "Text:A",
    ]


def test_large_image_split_into_many_reads() -> None:
    image = bytes.fromhex("1d 76 30 00 48 00 d0 07") + bytes(72 * 2000)
    tokenizer = Tokenizer()

    tokens = [t for i in range(0, len(image), 1024) for t in tokenizer.feed(image[i : i + 1024])]

    assert names(tokens) == ["GS v 0"]
    assert tokenizer.close() is None


@given(st.binary(max_size=2000))
def test_random_bytes_never_raise(data: bytes) -> None:
    tokens = tokens_of(data)

    consumed = b"".join(t.data if isinstance(t, Text) else t.raw for t in tokens)
    assert consumed == data


@given(st.binary(max_size=600), st.lists(st.integers(min_value=0, max_value=600), max_size=12))
def test_any_split_gives_the_same_tokens(data: bytes, cuts: list[int]) -> None:
    points = sorted({min(cut, len(data)) for cut in cuts} | {0, len(data)})
    reads = [data[a:b] for a, b in pairwise(points)]

    assert tokens_of(*reads) == tokens_of(data)
