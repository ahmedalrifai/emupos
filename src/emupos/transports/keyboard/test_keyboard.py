import time
from itertools import pairwise

from emupos.scanner.keys import Key, plan_keys
from emupos.transports.keyboard.keyboard import (
    system_keyboard,
    type_keys,
)


class FakeKeyboard:
    """Records when each key was pressed; refuses the keys in `refuse`."""

    def __init__(self, refuse: tuple[Key, ...] = ()) -> None:
        self.refuse = refuse
        self.presses: list[tuple[float, Key]] = []

    def check_ready(self) -> None:
        pass

    def press(self, key: Key) -> bool:
        self.presses.append((time.monotonic(), key))
        return key not in self.refuse


async def test_inter_key_delay_honoured_including_before_the_suffix() -> None:
    keyboard = FakeKeyboard()
    keys = plan_keys("123", "enter", unicode=False)

    accepted = await type_keys(keyboard, keys, inter_key_delay_ms=25)

    assert accepted == 4
    assert [key for _, key in keyboard.presses] == list(keys)
    times = [at for at, _ in keyboard.presses]
    assert all(later - earlier >= 0.025 for earlier, later in pairwise(times))


async def test_counts_only_accepted_keys() -> None:
    keys = plan_keys("121", "enter", unicode=False)
    keyboard = FakeKeyboard(refuse=(keys[0],))

    assert await type_keys(keyboard, keys, inter_key_delay_ms=0) == 2
    assert len(keyboard.presses) == 4


async def test_no_keys() -> None:
    assert await type_keys(FakeKeyboard(), (), inter_key_delay_ms=10) == 0


def test_system_keyboard_opens_nothing() -> None:
    assert hasattr(system_keyboard(), "check_ready")
