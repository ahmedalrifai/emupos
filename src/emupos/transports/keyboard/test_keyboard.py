import asyncio
import time
from collections.abc import Sequence
from itertools import pairwise

import pytest

from emupos.scanner.keys import Key, plan_keys
from emupos.transports.keyboard.keyboard import (
    system_keyboard,
    type_keys,
)


class FakeKeyboard:
    """Records when each key was pressed, and the scan steps; refuses the keys in `refuse`."""

    def __init__(self, refuse: tuple[Key, ...] = ()) -> None:
        self.refuse = refuse
        self.presses: list[tuple[float, Key]] = []
        self.calls: list[object] = []  # ("start", keys), each key, "end"

    def check_ready(self) -> None:
        pass

    def start_scan(self, keys: Sequence[Key]) -> None:
        self.calls.append(("start", tuple(keys)))

    def press(self, key: Key) -> bool:
        self.presses.append((time.monotonic(), key))
        self.calls.append(key)
        return key not in self.refuse

    def end_scan(self) -> None:
        self.calls.append("end")


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
    assert keyboard.calls[-1] == "end"


async def test_scan_steps_come_before_the_first_key_and_after_the_last() -> None:
    keyboard = FakeKeyboard()
    keys = plan_keys("12", "enter", unicode=True)

    await type_keys(keyboard, keys, inter_key_delay_ms=0)

    assert keyboard.calls == [("start", keys), *keys, "end"]


async def test_scan_ends_when_typing_is_cancelled() -> None:
    keyboard = FakeKeyboard()
    keys = plan_keys("123", "enter", unicode=False)
    typing = asyncio.create_task(type_keys(keyboard, keys, inter_key_delay_ms=1000))
    await asyncio.sleep(0.05)  # the first key is typed, the second waits for the delay

    typing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await typing

    assert keyboard.calls == [("start", keys), keys[0], "end"]


async def test_no_keys() -> None:
    assert await type_keys(FakeKeyboard(), (), inter_key_delay_ms=10) == 0


def test_system_keyboard_opens_nothing() -> None:
    assert hasattr(system_keyboard(), "check_ready")
