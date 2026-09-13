from io import BytesIO

import pytest
import zxingcpp
from hypothesis import given
from hypothesis import strategies as st
from PIL import Image

from emupos.barcodes.weighed import (
    PRESETS,
    WeighedBarcodeError,
    check_digit,
    generate,
    parse_layout,
    render_png,
)


def is_valid_ean13(digits: str) -> bool:
    """Independent check: the weighted sum of all 13 digits is a multiple of 10."""
    weights = [1, 3] * 6 + [1]
    return (
        len(digits) == 13
        and sum(int(d) * w for d, w in zip(digits, weights, strict=True)) % 10 == 0
    )


def rejection(layout: str, **values: int | None) -> WeighedBarcodeError:
    values.setdefault("item", 12345)
    with pytest.raises(WeighedBarcodeError) as caught:
        generate(layout, **values)
    return caught.value


# Layout patterns


def test_weight_layout_accepted() -> None:
    digits = generate("21IIIIIWWWWWC", item=12345, grams=1250)

    assert (digits[:2], digits[2:7], digits[7:12], digits[12]) == ("21", "12345", "01250", "6")


def test_custom_field_widths_accepted() -> None:
    assert generate("28IIIIWWWWWWC", item=1234, grams=12500) == "2812340125002"


# Layout validation


def test_wrong_length() -> None:
    error = rejection("21IIIIIWWWWC", grams=1250)

    assert "has 12 characters and 13 are required" in error.message


@pytest.mark.parametrize("layout", ["21IIIIIWWWWWW", "21CIIIIIWWWWW"])
def test_check_position_missing_or_misplaced(layout: str) -> None:
    assert "the check digit `C` must be the last character" in rejection(layout, grams=1).message


def test_both_weight_and_price_fields() -> None:
    error = rejection("21IIIIIWWPPPC", grams=1250)

    assert "either a `W` field or a `P` field, not both" in error.message


def test_split_field() -> None:
    assert "the `I` field is not contiguous" in rejection("21IIIIWWWWWIC", grams=1).message


@pytest.mark.parametrize(
    ("layout", "problem"),
    [
        ("21IIIIIWWWWWC0", "has 14 characters"),
        ("21IIIIXWWWWWC", "character `X` at position 7"),
        ("21iiiiiwwwwwc", "pattern letters are uppercase"),
        ("21CIIIIWWWWWC", "it has 2 `C`"),
        ("IIIIIIIWWWWWC", "must start with at least one literal digit"),
        ("21III5IWWWWWC", "digit at position 6 comes after a field"),
        ("21000000WWWWC", "no item field `I`"),
        ("21IIIIIIIIIIC", "neither a weight field `W` nor a price field `P`"),
        ("21WWIIIIIWWWC", "the `W` field is not contiguous"),
    ],
)
def test_every_listed_layout_problem_is_named(layout: str, problem: str) -> None:
    error = rejection(layout, grams=1)

    assert problem in error.message
    assert "21IIIIIWWWWWC" in error.fix
    assert "weight-21" in error.fix
    assert "price-23" in error.fix


# Built-in presets


def test_weight_preset() -> None:
    assert generate("weight-21", item=12345, grams=1250) == "2112345012506"


def test_price_preset() -> None:
    assert generate("price-23", item=12345, price_minor=1299) == "2312345012999"


def test_preset_behaves_exactly_as_its_pattern() -> None:
    for name, pattern in PRESETS.items():
        assert parse_layout(name) == parse_layout(pattern) == pattern


def test_unknown_preset() -> None:
    error = rejection("weight-99", grams=1250)

    assert "weight-99" in error.message
    assert "weight-21" in error.fix
    assert "price-23" in error.fix


# Field values


def test_zero_padding() -> None:
    assert generate("21IIIIIWWWWWC", item=42, grams=750) == "2100042007505"


def test_price_in_minor_units() -> None:
    digits = generate("23IIIIIPPPPPC", item=12345, price_minor=1299)

    assert digits[7:12] == "01299"  # positions 8 to 12


# Value kind matches the layout


def test_price_given_for_a_weight_layout() -> None:
    error = rejection("21IIIIIWWWWWC", price_minor=1299)

    assert "this layout requires a weight" in error.message
    assert "price" in error.message


def test_weight_missing() -> None:
    assert "a weight is required" in rejection("21IIIIIWWWWWC").message


def test_price_missing_names_the_api_field() -> None:
    assert "price is required by this layout (`price_minor`)" in rejection("21IIIIIPPPPPC").message


def test_weight_given_for_a_price_layout() -> None:
    assert "this layout requires a price" in rejection("price-23", grams=1250).message


def test_weight_and_price_together_rejected() -> None:
    assert "not both" in rejection("weight-21", grams=1250, price_minor=1299).message


def test_missing_item_rejected() -> None:
    error = rejection("weight-21", item=None, grams=1250)

    assert "item code (`item`) is required" in error.message


# Values that do not fit their field


def test_weight_overflow() -> None:
    error = rejection("21IIIIIWWWWWC", grams=100000)

    assert "the 5-digit weight field holds at most 99999 g" in error.message


def test_item_code_overflow() -> None:
    error = rejection("21IIIIIWWWWWC", item=123456, grams=1250)

    assert "the item field holds at most 5 digits, up to 99999" in error.message


def test_negative_price() -> None:
    error = rejection("23IIIIIPPPPPC", price_minor=-5)

    assert "price -5 is negative" in error.message
    assert error.fix


# EAN-13 check digit


def test_check_digit_computed() -> None:
    assert check_digit("211234501250") == "6"  # weighted sum 44


def test_sum_already_a_multiple_of_10() -> None:
    assert check_digit("211234500080") == "0"  # weighted sum 40


@pytest.mark.parametrize(
    "digits",
    [
        "2112345012506",
        "2812340125002",
        "2112345000800",
        "2312345012999",
        "2100042007505",
        "4006381333931",  # a retail EAN-13 printed on a real product
    ],
)
def test_spec_examples_carry_the_computed_check_digit(digits: str) -> None:
    assert check_digit(digits[:12]) == digits[12]
    assert is_valid_ean13(digits)


@given(
    item=st.integers(0, 99999),
    value=st.integers(0, 99999),
    preset=st.sampled_from(sorted(PRESETS)),
)
def test_every_generated_barcode_validates(item: int, value: int, preset: str) -> None:
    kind = {"weight-21": "grams", "price-23": "price_minor"}[preset]

    digits = generate(preset, item=item, **{kind: value})

    assert is_valid_ean13(digits)


@given(prefix=st.integers(1, 10), data=st.data())
def test_custom_layouts_generate_valid_barcodes(prefix: int, data: st.DataObject) -> None:
    item_width = data.draw(st.integers(1, 11 - prefix))
    value_width = 12 - prefix - item_width
    pattern = "2" * prefix + "I" * item_width + "W" * value_width + "C"
    item = data.draw(st.integers(0, 10**item_width - 1))
    grams = data.draw(st.integers(0, 10**value_width - 1))

    digits = generate(pattern, item=item, grams=grams)

    assert digits.startswith("2" * prefix)
    assert is_valid_ean13(digits)


# Barcode image output


def test_saved_label_image_decodes_to_the_digits() -> None:
    png = render_png("2112345012506")

    image = Image.open(BytesIO(png))
    assert image.format == "PNG"
    results = zxingcpp.read_barcodes(image)
    assert [(result.format, result.text) for result in results] == [
        (zxingcpp.BarcodeFormat.EAN13, "2112345012506")
    ]


@pytest.mark.parametrize("digits", ["2112345012505", "211234501250", "21123450125O6"])
def test_image_refuses_digits_that_are_not_a_valid_ean13(digits: str) -> None:
    with pytest.raises(ValueError, match="valid EAN-13 check digit"):
        render_png(digits)
