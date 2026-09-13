import pytest

from emupos.scale.weights import parse_weight


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
