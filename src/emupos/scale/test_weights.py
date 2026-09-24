from decimal import Decimal

import pytest

from emupos.config import ScaleUnit
from emupos.scale.weights import grams_from_unit, in_unit, parse_weight


@pytest.mark.parametrize(
    ("text", "grams"),
    [
        ("1.25kg", 1250),
        ("1250g", 1250),
        ("0.8kg", 800),
        ("15kg", 15000),
        ("-100g", -100),
        ("0g", 0),
    ],
)
def test_weights_convert_exactly_to_grams(text: str, grams: int) -> None:
    assert parse_weight(text) == grams


def test_sub_gram_weight_is_rejected() -> None:
    with pytest.raises(ValueError, match="whole grams"):
        parse_weight("1.2505kg")


@pytest.mark.parametrize("text", ["1.25", "1.25lb", "1.25 kg", "1.25KG", "kg", "1,25kg", ""])
def test_other_units_and_missing_unit_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match=r"e\.g\. 1\.25kg or 1250g"):
        parse_weight(text)


@pytest.mark.parametrize(
    ("grams", "unit", "decimals", "count_by", "expected"),
    [
        (0, "kg_", 3, 5, "0.000"),
        (5, "kg_", 3, 5, "0.005"),  # one count-by
        (1252, "kg_", 3, 5, "1.250"),  # below half a count-by, down
        (1253, "kg_", 3, 5, "1.255"),  # half a count-by, away from zero
        (-1253, "kg_", 3, 5, "-1.255"),  # and away from zero below zero too
        (1250, "lb_", 2, 1, "2.76"),
        (15000, "lb_", 2, 1, "33.07"),
        (999999995, "kg_", 3, 5, "999999.995"),  # fills the SMA weight field exactly
    ],
)
def test_a_weight_in_its_unit(
    grams: int, unit: str, decimals: int, count_by: int, expected: str
) -> None:
    entry = ScaleUnit.model_validate({"unit": unit, "decimals": decimals, "count_by": count_by})

    assert f"{in_unit(grams, entry):f}" == expected


def test_high_resolution_adds_a_decimal_place() -> None:
    entry = ScaleUnit.model_validate({"unit": "kg_", "decimals": 3, "count_by": 5})

    assert f"{in_unit(1252, entry, high_resolution=True):f}" == "1.2520"


@pytest.mark.parametrize(("value", "grams"), [("0.200", 200), ("1.5", 1500), ("0.0001", 0)])
def test_a_weight_given_in_a_unit_becomes_whole_grams(value: str, grams: int) -> None:
    entry = ScaleUnit.model_validate({"unit": "kg_", "decimals": 3, "count_by": 5})

    assert grams_from_unit(Decimal(value), entry) == grams
