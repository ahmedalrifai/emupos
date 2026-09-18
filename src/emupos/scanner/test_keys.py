import json

import pytest

from emupos.scanner.keys import (
    US_LAYOUT,
    Key,
    PhysicalKey,
    UnicodeText,
    key_from_json,
    key_to_json,
    plan_keys,
)

ENTER, TAB = PhysicalKey(0x28), PhysicalKey(0x2B)


def test_us_layout_covers_printable_ascii_with_distinct_keys() -> None:
    assert sorted(US_LAYOUT) == [chr(code) for code in range(0x20, 0x7F)]
    assert len(set(US_LAYOUT.values())) == len(US_LAYOUT)


@pytest.mark.parametrize(
    ("char", "usage", "shift"),
    # HID Usage Tables, Keyboard/Keypad page (0x07)
    [
        ("a", 0x04, False),
        ("Z", 0x1D, True),
        ("1", 0x1E, False),
        ("0", 0x27, False),
        (")", 0x27, True),
        (" ", 0x2C, False),
        ("_", 0x2D, True),
        ("|", 0x31, True),
        (";", 0x33, False),
        ('"', 0x34, True),
        ("~", 0x35, True),
        ("/", 0x38, False),
        ("?", 0x38, True),
    ],
)
def test_hid_usage_of_characters(char: str, usage: int, shift: bool) -> None:
    assert US_LAYOUT[char] == PhysicalKey(usage, shift)


def test_mixed_characters_then_enter() -> None:
    assert plan_keys("Ab1-", "enter", unicode=False) == (
        PhysicalKey(0x04, shift=True),
        PhysicalKey(0x05),
        PhysicalKey(0x1E),
        PhysicalKey(0x2D),
        ENTER,
    )


def test_tab_and_no_suffix() -> None:
    assert plan_keys("1", "tab", unicode=False) == (PhysicalKey(0x1E), TAB)
    assert plan_keys("1", "none", unicode=False) == (PhysicalKey(0x1E),)


def test_unicode_characters_then_suffix_key() -> None:
    assert plan_keys("ك-4", "enter", unicode=True) == (
        UnicodeText("ك"),
        UnicodeText("-"),
        UnicodeText("4"),
        ENTER,
    )


def test_non_ascii_without_unicode_raises() -> None:
    with pytest.raises(ValueError, match="US keyboard layout"):
        plan_keys("ك", "enter", unicode=False)


@pytest.mark.parametrize(
    "key",
    [PhysicalKey(0x04), PhysicalKey(0x04, shift=True), ENTER, UnicodeText("ك"), UnicodeText("é")],
)
def test_key_json_round_trip(key: Key) -> None:
    assert key_from_json(json.loads(json.dumps(key_to_json(key)))) == key


def test_key_to_json_shape() -> None:
    assert key_to_json(PhysicalKey(0x04, shift=True)) == {"usage": 4, "shift": True}
    assert key_to_json(UnicodeText("é")) == {"char": "é"}


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"usage": 4},  # no shift
        {"usage": True, "shift": False},  # a bool is not a usage ID
        {"usage": -1, "shift": False},
        {"usage": "4", "shift": False},
        {"char": ""},
        {"char": "ab"},
        {"char": 4},
        "usage",
        None,
    ],
)
def test_key_from_json_refuses_malformed(value: object) -> None:
    with pytest.raises(ValueError, match="not a key"):
        key_from_json(value)
