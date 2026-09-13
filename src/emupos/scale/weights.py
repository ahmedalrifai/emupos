"""Weight values typed by people, shared by `emupos scale set` and `emupos barcode weighed`."""

import re
from decimal import Decimal

_WEIGHT = re.compile(r"(-?[0-9]+(?:\.[0-9]+)?)(kg|g)")
_FORMS = "write the weight with its unit, e.g. 1.25kg or 1250g"


def parse_weight(text: str) -> int:
    """Convert `1.25kg` or `1250g` to whole grams, exactly (cli spec, "Scale commands").

    Negative values are allowed so that an under-zero reading can be set; callers that need a
    non-negative weight check it themselves.
    """
    match = _WEIGHT.fullmatch(text)
    if match is None:
        raise ValueError(f"`{text}` is not a weight; {_FORMS}")
    grams = Decimal(match[1]) * (1000 if match[2] == "kg" else 1)
    if grams != grams.to_integral_value():
        raise ValueError(
            f"`{text}` is {grams.normalize():f} g, but weights are whole grams; {_FORMS}"
        )
    return int(grams)
