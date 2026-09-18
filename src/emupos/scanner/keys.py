"""Keys a keyboard-wedge scan presses, independent of the operating system.

Physical keys are named by their USB HID usage ID (HID Usage Tables, Keyboard/Keypad page
0x07): the id a real USB scanner sends, and one every OS maps from. Which character a key
produces is then up to the OS's active layout, exactly as with a real scanner (design D10).
"""

from dataclasses import dataclass
from typing import Literal

type Suffix = Literal["enter", "tab", "none"]

ENTER = 0x28
TAB = 0x2B
LEFT_SHIFT = 0xE1


@dataclass(frozen=True, slots=True)
class PhysicalKey:
    usage: int  # HID usage ID on page 0x07, e.g. 0x04 for the A key
    shift: bool = False


@dataclass(frozen=True, slots=True)
class UnicodeText:
    char: str  # one code point, typed exactly whatever the layout


type Key = PhysicalKey | UnicodeText

# (first usage, characters, the same keys with Shift) on the US layout, in usage order.
_US_ROWS = (
    (0x04, "abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    (0x1E, "1234567890", "!@#$%^&*()"),
    (0x2C, " -=[]\\", " _+{}|"),  # 0x2C space, 0x2D minus ... 0x31 backslash
    (0x33, ";'`,./", ':"~<>?'),  # 0x32 (Non-US #) is not on the US layout
)

# Every printable ASCII character (20 to 7e) -> the US key that types it.
US_LAYOUT: dict[str, PhysicalKey] = {}
for _first, _plain, _shifted in _US_ROWS:
    for _offset, (_char, _shifted_char) in enumerate(zip(_plain, _shifted, strict=True)):
        US_LAYOUT.setdefault(_char, PhysicalKey(_first + _offset))
        US_LAYOUT.setdefault(_shifted_char, PhysicalKey(_first + _offset, shift=True))

SUFFIX_KEYS: dict[Suffix, PhysicalKey | None] = {
    "enter": PhysicalKey(ENTER),
    "tab": PhysicalKey(TAB),
    "none": None,
}


def key_to_json(key: Key) -> dict[str, object]:
    """One key on the wire: a physical key, or one exact character (control-api spec)."""
    if isinstance(key, PhysicalKey):
        return {"usage": key.usage, "shift": key.shift}
    return {"char": key.char}


def key_from_json(value: object) -> Key:
    """The key `key_to_json` wrote. Raises ValueError for anything else."""
    match value:  # pyright: ignore[reportMatchNotExhaustive] -- anything unmatched is a ValueError
        case {"char": str(char)} if len(char) == 1:
            return UnicodeText(char)
        # bool is an int: `"usage": true` is not a usage ID.
        case {"usage": int(usage), "shift": bool(shift)} if (
            not isinstance(usage, bool) and usage >= 0
        ):
            return PhysicalKey(usage, shift)
    raise ValueError(f"not a key: {value!r}")


def plan_keys(data: str, suffix: Suffix, unicode: bool) -> tuple[Key, ...]:
    """The keys for one scan: each character, then the suffix key.

    Raises ValueError for a character outside printable ASCII when `unicode` is false.
    """
    keys: list[Key] = []
    for char in data:
        if unicode:
            keys.append(UnicodeText(char))
        elif char in US_LAYOUT:
            keys.append(US_LAYOUT[char])
        else:
            raise ValueError(f"{char!r} is not on the US keyboard layout")
    if (suffix_key := SUFFIX_KEYS[suffix]) is not None:
        keys.append(suffix_key)
    return tuple(keys)
