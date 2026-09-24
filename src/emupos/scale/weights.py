"""Weight values: the ones people type, and the ones a scale reports in a unit of measure.

`parse_weight` is shared by `emupos scale set` and `emupos barcode weighed`. The unit conversions
below are used by protocols that report a weight in a unit the profile names, and use the exact
definition of each unit, so a pound is 453.59237 g and nothing is approximated.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

from emupos.config import ScaleUnit, SmaUnit

# Grams in one of each unit, exactly. SMA SCP-0499 section 7 names the units; the masses are their
# SI definitions.
GRAMS_PER_UNIT: dict[SmaUnit, Decimal] = {
    "kg_": Decimal(1000),
    "g__": Decimal(1),
    "mg_": Decimal("0.001"),
    "lb_": Decimal("453.59237"),
    "oz_": Decimal("28.349523125"),
    "ozt": Decimal("31.1034768"),
    "ct_": Decimal("0.2"),
    "gn_": Decimal("0.06479891"),
    "dwt": Decimal("1.55517384"),
    "t__": Decimal(1000000),
    "ton": Decimal("907184.74"),
}

_WEIGHT = re.compile(r"(-?[0-9]+(?:\.[0-9]+)?)(kg|g)")
_FORMS = "write the weight with its unit, e.g. 1.25kg or 1250g"


def in_unit(grams: int, unit: ScaleUnit, *, high_resolution: bool = False) -> Decimal:
    """Grams as a value in `unit`, rounded to its count-by, ties away from zero.

    A high-resolution reading counts by a tenth of the count-by and is written with one more
    decimal place, which is what SMA SCP-0499 means by "10x" for its H and Q commands.
    """
    decimals = unit.decimals + (1 if high_resolution else 0)
    step = Decimal(unit.count_by).scaleb(-decimals)  # e.g. count_by 5, 3 decimals -> 0.005
    value = Decimal(grams) / GRAMS_PER_UNIT[unit.unit]
    steps = (value / step).quantize(Decimal(1), ROUND_HALF_UP)
    return (steps * step).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)


def grams_from_unit(value: Decimal, unit: ScaleUnit) -> int:
    """A weight given in `unit` as whole grams, rounded the same way."""
    return int((value * GRAMS_PER_UNIT[unit.unit]).quantize(Decimal(1), ROUND_HALF_UP))


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
