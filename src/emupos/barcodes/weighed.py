"""Weighed-item EAN-13 barcodes from layout patterns (weighed-item-barcodes spec, design D9).

A layout is a 13-character pattern such as `21IIIIIWWWWWC`: literal prefix digits, an `I` item
field, a `W` weight field (grams) or a `P` price field (minor currency units), and the check
digit `C` last. Pure: digits and PNG bytes are returned, nothing is written.
"""

import re
from io import BytesIO

from barcode import EAN13
from barcode.writer import ImageWriter

PRESETS = {"weight-21": "21IIIIIWWWWWC", "price-23": "23IIIIIPPPPPC"}
LAYOUT_FIX = (
    "use a 13-character pattern such as 21IIIIIWWWWWC (prefix digits, an I item field, "
    "a W weight or P price field, and the check digit C last), or a preset: " + ", ".join(PRESETS)
)
_VALUE_NAMES = {"W": ("weight", "grams", " g"), "P": ("price", "price_minor", "")}


class WeighedBarcodeError(Exception):
    """A layout or value was rejected; `fix` describes a valid input."""

    def __init__(self, message: str, fix: str) -> None:
        self.message = message
        self.fix = fix
        super().__init__(f"{message}; {fix}")


def parse_layout(layout: str) -> str:
    """Resolve a preset name and validate the pattern ("Layout validation")."""
    if layout in PRESETS:
        return PRESETS[layout]
    if "-" in layout:
        raise WeighedBarcodeError(f"unknown layout preset `{layout}`", LAYOUT_FIX)
    problem = _pattern_problem(layout)
    if problem is not None:
        raise WeighedBarcodeError(f"invalid layout `{layout}`: {problem}", LAYOUT_FIX)
    return layout


def _pattern_problem(pattern: str) -> str | None:
    if len(pattern) != 13:
        return f"it has {len(pattern)} characters and 13 are required"
    for position, char in enumerate(pattern, start=1):
        if char not in "0123456789IWPC":
            uppercase = "; pattern letters are uppercase" if char.upper() in "IWPC" else ""
            return (
                f"character `{char}` at position {position} is not a digit, I, W, P or C{uppercase}"
            )
    checks = pattern.count("C")
    if checks == 0:
        return "it has no check digit; the check digit `C` must be the last character"
    if checks > 1:
        return f"it has {checks} `C`; the check digit `C` must be the last character, and only once"
    if not pattern.endswith("C"):
        return f"`C` is at position {pattern.index('C') + 1}; the check digit `C` must be the last character"
    prefix_length = len(pattern) - len(pattern.lstrip("0123456789"))
    if prefix_length == 0:
        return "it must start with at least one literal digit (the prefix)"
    after_prefix = re.search(r"[0-9]", pattern[prefix_length:])
    if after_prefix:
        position = prefix_length + after_prefix.start() + 1
        return f"digit at position {position} comes after a field; literal digits are only allowed at the start"
    if "I" not in pattern:
        return "it has no item field `I`"
    if "W" not in pattern and "P" not in pattern:
        return "it has neither a weight field `W` nor a price field `P`"
    if "W" in pattern and "P" in pattern:
        return "a layout contains either a `W` field or a `P` field, not both"
    for letter in "IWP":
        if letter in pattern and letter * pattern.count(letter) not in pattern:
            return f"the `{letter}` field is not contiguous"
    return None


def generate(
    layout: str, *, item: int | None, grams: int | None = None, price_minor: int | None = None
) -> str:
    """The 13 digits for an item and its weight or price ("Field values", "EAN-13 check digit")."""
    pattern = parse_layout(layout)
    wanted = "W" if "W" in pattern else "P"
    other = "P" if wanted == "W" else "W"
    name, key, _ = _VALUE_NAMES[wanted]
    fix = f"layout `{layout}` takes an item code (`item`) and a {name} (`{key}`)"
    values = {"W": grams, "P": price_minor}
    if item is None:
        raise WeighedBarcodeError("an item code (`item`) is required", fix)
    if grams is not None and price_minor is not None:
        raise WeighedBarcodeError("give either a weight or a price, not both", fix)
    if values[other] is not None:
        other_name, other_key, _ = _VALUE_NAMES[other]
        raise WeighedBarcodeError(
            f"this layout requires a {name}, not a {other_name} (`{other_key}`)", fix
        )
    value = values[wanted]
    if value is None:
        raise WeighedBarcodeError(f"a {name} is required by this layout (`{key}`)", fix)
    digits = _fill(_fill(pattern, "I", item), wanted, value)
    return digits[:12] + check_digit(digits[:12])


def _fill(pattern: str, letter: str, value: int) -> str:
    """Write `value` zero-padded into the field of `letter` ("Values that do not fit their field")."""
    width = pattern.count(letter)
    largest = 10**width - 1
    if letter == "I":
        name, unit = "item", ""
        holds = f"the item field holds at most {width} digits, up to {largest}"
    else:
        name, _, unit = _VALUE_NAMES[letter]
        holds = f"the {width}-digit {name} field holds at most {largest}{unit}"
    if not 0 <= value <= largest:
        problem = "is negative" if value < 0 else "does not fit"
        raise WeighedBarcodeError(
            f"{name} {value}{unit} {problem}: {holds}",
            f"give a {name} from 0 to {largest}{unit}, or use a layout with a wider {name} field",
        )
    start = pattern.index(letter)
    return pattern[:start] + f"{value:0{width}d}" + pattern[start + width :]


def check_digit(first_12: str) -> str:
    """EAN-13 check digit: weights 1, 3, 1, 3... from the leftmost digit ("EAN-13 check digit")."""
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(first_12))
    return str((10 - total % 10) % 10)


def render_png(digits: str) -> bytes:
    """A PNG of the EAN-13 symbol with the digits printed beneath it ("Barcode image output")."""
    if not re.fullmatch(r"[0-9]{13}", digits) or check_digit(digits[:12]) != digits[12]:
        # python-barcode would silently replace a wrong check digit and draw a different code.
        raise ValueError(f"`{digits}` is not 13 digits with a valid EAN-13 check digit")
    buffer = BytesIO()
    EAN13(digits, writer=ImageWriter()).write(buffer)  # pyright: ignore[reportUnknownMemberType]
    return buffer.getvalue()
