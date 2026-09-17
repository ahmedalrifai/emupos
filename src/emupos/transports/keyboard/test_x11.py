"""X11 keyboard checks with the environment and library loader replaced; no X server needed."""

import ctypes
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pytest

from emupos.scanner.keys import ENTER, LEFT_SHIFT, TAB, US_LAYOUT, PhysicalKey, plan_keys
from emupos.transports.keyboard import x11
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError, type_keys


def refusal(
    monkeypatch: pytest.MonkeyPatch, session: str | None, display: str | None
) -> KeyboardUnavailableError:
    for name, value in (("XDG_SESSION_TYPE", session), ("DISPLAY", display)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    with pytest.raises(KeyboardUnavailableError) as caught:
        x11.X11Keyboard().check_ready()
    return caught.value


def missing(*names: str) -> object:
    def load(name: str) -> object:
        if name in names:
            raise OSError(f"{name}: cannot open shared object file")
        return object()

    return load


def test_wayland_session(monkeypatch: pytest.MonkeyPatch) -> None:
    error = refusal(monkeypatch, "wayland", ":0")  # XWayland sets DISPLAY too

    assert "Wayland" in error.message
    assert "mode: serial" in error.fix


def test_no_display(monkeypatch: pytest.MonkeyPatch) -> None:
    error = refusal(monkeypatch, "x11", None)

    assert "DISPLAY" in error.message
    assert "mode: serial" in error.fix


def test_libxtst_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(x11, "_load_library", missing("libXtst.so.6"))

    error = refusal(monkeypatch, "x11", ":0")

    assert "libXtst" in error.message
    assert "libxtst6" in error.fix
    assert "libXtst" in error.fix


def test_libx11_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(x11, "_load_library", missing("libX11.so.6", "libXtst.so.6"))

    assert "libx11-6" in refusal(monkeypatch, None, ":0").fix


def test_press_before_check_ready_types_nothing() -> None:
    assert not x11.X11Keyboard().press(PhysicalKey(0x04))


@pytest.mark.parametrize(
    ("usage", "keycode"),
    # evdev KEY_* from linux/input-event-codes.h, plus 8
    [
        (US_LAYOUT["a"].usage, 30 + 8),
        (US_LAYOUT["1"].usage, 2 + 8),
        (US_LAYOUT["0"].usage, 11 + 8),
        (US_LAYOUT["-"].usage, 12 + 8),
        (US_LAYOUT["z"].usage, 44 + 8),
        (US_LAYOUT["/"].usage, 53 + 8),
        (US_LAYOUT[" "].usage, 57 + 8),
        (ENTER, 28 + 8),
        (TAB, 15 + 8),
        (LEFT_SHIFT, 42 + 8),
    ],
)
def test_keycodes(usage: int, keycode: int) -> None:
    assert x11.KEYCODES[usage] == keycode


def test_every_us_key_has_a_keycode() -> None:
    assert {key.usage for key in US_LAYOUT.values()} <= set(x11.KEYCODES)


# --- typing, with libX11, libXtst and libxkbcommon replaced by fakes ------------------------

SHIFT_L, KP_ADD, ARABIC_SHEEN, F13 = 0xFFE1, 0xFFAB, 0x5D4, 0xFFCA
SHIFT_KEYCODE = 42 + 8
ROOT, OWN_WINDOW, OWN_CLIENT, APP_CLIENT = 0x100, 0x400001, 0x400000, 0x200000
FROM_CLIENT, START_OF_DATA = 1, 4  # XRecordInterceptData categories
# Two groups, two levels each: group 1 is a US layout, group 2 an Arabic one.
KEYMAP = {
    10: [ord("1"), ord("!"), ord("1"), ord("!")],
    38: [ord("a"), ord("A"), ARABIC_SHEEN, ARABIC_SHEEN],
    SHIFT_KEYCODE: [SHIFT_L] * 4,
    86: [KP_ADD] * 4,
}


def keysym_to_utf32(keysym: int) -> int:
    if keysym == ARABIC_SHEEN:
        return ord("ش")
    if keysym == KP_ADD:
        return ord("+")
    if keysym >> 24 == 1:
        return keysym & 0xFFFFFF
    return keysym if 0x20 <= keysym <= 0xFF else 0


class FakeX11:
    """The libX11 calls X11Keyboard makes, on a small keymap."""

    def __init__(self, spare: Sequence[int], group: int, caps: bool) -> None:
        self.keymap = {**KEYMAP, **{keycode: [0] * 4 for keycode in spare}}
        self.group = group
        self.locked = x11.LOCK_MASK if caps else 0
        self.lock_calls: list[tuple[int, int]] = []
        self.mapping_changes = 0
        self.atoms: dict[str, int] = {}
        self.properties: dict[int, list[int]] = {}  # of the root window, by atom
        self.owners: dict[int, int] = {}  # selection atom -> owner window

    def atom(self, name: str) -> int:
        return self.atoms.setdefault(name, 1000 + len(self.atoms))

    def own_bindings(self) -> list[int] | None:
        """The root property of the emupos under test."""
        atom = next(atom for atom, owner in self.owners.items() if owner == OWN_WINDOW)
        return self.properties.get(atom)

    def current_keymap(self, _x11: object, _display: object) -> dict[int, list[int]]:
        return {keycode: list(keysyms) for keycode, keysyms in self.keymap.items()}

    def list_properties(self, _x11: object, _display: object, _window: object) -> list[int]:
        return list(self.properties)

    def atom_name(self, _x11: object, _display: object, atom: int) -> str:
        return next(name for name, known in self.atoms.items() if known == atom)

    def read_cardinals(
        self, _x11: object, _display: object, _window: object, atom: int
    ) -> list[int]:
        return self.properties.get(atom, [])

    def XInternAtom(self, _display: int, name: bytes, _only_if_exists: int) -> int:  # noqa: N802
        return self.atom(name.decode())

    def XDefaultRootWindow(self, _display: int) -> int:  # noqa: N802
        return ROOT

    def XCreateSimpleWindow(self, *_: object) -> int:  # noqa: N802
        return OWN_WINDOW

    def XSetSelectionOwner(self, _display: int, atom: int, window: int, _time: int) -> None:  # noqa: N802
        self.owners[atom] = window

    def XGetSelectionOwner(self, _display: int, atom: int) -> int:  # noqa: N802
        return self.owners.get(atom, 0)

    def XChangeProperty(  # noqa: N802
        self,
        _display: int,
        _window: int,
        atom: int,
        _type: int,
        _format: int,
        _mode: int,
        values: Sequence[int],
        count: int,
    ) -> None:
        self.properties[atom] = list(values[:count])

    def XDeleteProperty(self, _display: int, _window: int, atom: int) -> None:  # noqa: N802
        self.properties.pop(atom, None)

    def XSetErrorHandler(self, _handler: object) -> None:  # noqa: N802
        pass

    def XOpenDisplay(self, _name: object) -> int:  # noqa: N802
        return 1

    def XSync(self, *_: object) -> None:  # noqa: N802
        pass

    def XFlush(self, *_: object) -> None:  # noqa: N802
        pass

    def XChangeKeyboardMapping(  # noqa: N802
        self, _display: int, keycode: int, per_keycode: int, keysyms: Sequence[int], _count: int
    ) -> None:
        self.keymap[keycode] = [*keysyms[:per_keycode], *[0] * (4 - per_keycode)]
        self.mapping_changes += 1

    def XkbGetState(self, _display: int, _device: int, state: ctypes.Array[ctypes.c_char]) -> int:  # noqa: N802
        state[0], state[9] = bytes([self.group]), bytes([self.locked])
        return 0

    def XkbLockModifiers(self, _display: int, _device: int, affect: int, values: int) -> int:  # noqa: N802
        self.lock_calls.append((affect, values))
        self.locked = self.locked & ~affect | values
        return 1


class FakeXtst:
    def __init__(self) -> None:
        self.pressed: list[int] = []

    def XTestQueryExtension(self, *_: object) -> int:  # noqa: N802
        return 1

    def XTestFakeKeyEvent(self, _display: int, keycode: int, down: int, _delay: int) -> int:  # noqa: N802
        if down:
            self.pressed.append(keycode)
        return 1


class FakeWatch:
    """Reports that the app has read the keymap once it was polled `reads_after_polls` times."""

    def __init__(self, reads_after_polls: int | None) -> None:
        self.reads_after_polls = reads_after_polls
        self.polls = 0

    def poll(self) -> None:
        self.polls += 1

    def has_read(self, _client: int, _changes: int) -> bool:
        return self.reads_after_polls is not None and self.polls >= self.reads_after_polls


@dataclass
class Setup:
    keyboard: x11.X11Keyboard
    x11: FakeX11
    xtst: FakeXtst
    at_exit: list[Callable[[], None]]

    async def type_scan(self, text: str) -> None:
        await type_keys(self.keyboard, plan_keys(text, "none", unicode=True), 0)

    def type(self, text: str, unicode: bool = True) -> list[bool]:
        keys = plan_keys(text, "none", unicode=unicode)
        self.keyboard.start_scan(keys)
        try:
            return [self.keyboard.press(key) for key in keys]
        finally:
            self.keyboard.end_scan()


def ready_keyboard(
    monkeypatch: pytest.MonkeyPatch,
    spare: Sequence[int] = (200, 201),
    group: int = 0,
    caps: bool = False,
    xkbcommon: bool = True,
    watch: FakeWatch | None = None,
    focused: int | None = APP_CLIENT,
    before: Callable[[FakeX11], None] | None = None,
) -> Setup:
    fake_x11, fake_xtst = FakeX11(spare, group, caps), FakeXtst()
    at_exit: list[Callable[[], None]] = []

    def resource_ids(_display: int) -> tuple[int, int]:
        return OWN_CLIENT, 0x1FFFFF

    def focused_client(*_: object) -> int | None:
        return focused

    def start_watch(*_: object) -> FakeWatch | None:
        return watch

    monkeypatch.setattr(x11, "_resource_ids", resource_ids)
    monkeypatch.setattr(x11, "_focused_client", focused_client)
    monkeypatch.setattr(x11.KeymapWatch, "start", start_watch)
    monkeypatch.setattr(x11, "_list_properties", fake_x11.list_properties)
    monkeypatch.setattr(x11, "_atom_name", fake_x11.atom_name)
    monkeypatch.setattr(x11, "_read_cardinals", fake_x11.read_cardinals)
    if before is not None:
        before(fake_x11)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(x11, "load_libraries", lambda: (fake_x11, fake_xtst))
    monkeypatch.setattr(x11, "load_keysym_to_utf32", lambda: keysym_to_utf32 if xkbcommon else None)
    monkeypatch.setattr(x11, "_keymap", fake_x11.current_keymap)
    monkeypatch.setattr(x11.atexit, "register", at_exit.append)
    keyboard = x11.X11Keyboard()
    keyboard.check_ready()
    return Setup(keyboard, fake_x11, fake_xtst, at_exit)


def test_layout_key_types_a_character_without_changing_the_keymap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = ready_keyboard(monkeypatch)

    assert setup.type("a1") == [True, True]
    assert setup.xtst.pressed == [38, 10]
    assert setup.x11.mapping_changes == 0


def test_shift_level_of_a_layout_key(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch)

    setup.type("A!")

    assert setup.xtst.pressed == [SHIFT_KEYCODE, 38, SHIFT_KEYCODE, 10]
    assert setup.x11.mapping_changes == 0


def test_keypad_key_is_not_used(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch)

    setup.type("+")

    assert setup.xtst.pressed == [201]
    assert setup.x11.keymap[201][:2] == [ord("+"), ord("+")]


def test_second_group_when_it_is_active(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch, group=1)

    setup.type("شa")

    assert setup.xtst.pressed == [38, 201]  # group 2 has no `a`
    assert setup.x11.keymap[201][:2] == [ord("a"), ord("a")]


def test_missing_capital_letter_is_bound_on_both_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch)

    setup.type("Z")

    assert setup.x11.keymap[201][:2] == [ord("Z"), ord("Z")]  # a lone `Z` types `z` unshifted


def test_missing_characters_are_bound_before_the_first_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = ready_keyboard(monkeypatch)
    keys = plan_keys("كوك", "none", unicode=True)

    setup.keyboard.start_scan(keys)
    assert setup.x11.mapping_changes == 2
    for key in keys:
        setup.keyboard.press(key)
    setup.keyboard.end_scan()

    assert setup.xtst.pressed == [201, 200, 201]
    assert setup.x11.mapping_changes == 2  # the second ك is not bound again


def test_characters_are_bound_again_after_the_keymap_is_reloaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = ready_keyboard(monkeypatch)
    setup.type("é")
    setup.x11.keymap[201] = [0] * 4  # setxkbmap while emupos runs

    setup.type("é")

    assert setup.xtst.pressed == [201, 201]
    assert setup.x11.keymap[201][:2] == [ord("é"), ord("é")]


def test_least_recently_used_spare_keycode_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch)

    assert all(setup.type("éüéß"))

    assert setup.xtst.pressed == [201, 200, 201, 200]  # ß takes ü's: é was typed later
    assert setup.x11.keymap[200][:2] == [ord("ß"), ord("ß")]


def test_no_spare_keycode_types_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch, spare=())

    assert setup.type("é") == [False]
    assert setup.xtst.pressed == []


def test_without_libxkbcommon_every_character_uses_a_spare_keycode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = ready_keyboard(monkeypatch, xkbcommon=False)

    setup.type("a")

    assert setup.xtst.pressed == [201]
    assert setup.x11.keymap[201][:2] == [ord("a"), ord("a")]


def test_caps_lock_is_off_during_a_unicode_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch, caps=True)
    keys = plan_keys("a", "none", unicode=True)

    setup.keyboard.start_scan(keys)
    assert not setup.x11.locked
    setup.keyboard.end_scan()

    assert setup.x11.lock_calls == [(x11.LOCK_MASK, 0), (x11.LOCK_MASK, x11.LOCK_MASK)]


@pytest.mark.parametrize(("caps", "unicode"), [(True, False), (False, True)])
def test_caps_lock_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, caps: bool, unicode: bool
) -> None:
    setup = ready_keyboard(monkeypatch, caps=caps)

    setup.type("a", unicode=unicode)

    assert setup.x11.lock_calls == []


def test_caps_lock_comes_back_when_the_last_open_scan_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = ready_keyboard(monkeypatch, caps=True)
    keyboard = setup.keyboard

    keyboard.start_scan(plan_keys("a", "none", unicode=True))
    keyboard.start_scan(plan_keys("b", "none", unicode=True))
    keyboard.end_scan()
    assert not setup.x11.locked
    keyboard.end_scan()

    assert setup.x11.lock_calls == [(x11.LOCK_MASK, 0), (x11.LOCK_MASK, x11.LOCK_MASK)]


def test_exit_clears_the_spare_keycodes(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch)
    setup.type("éü")

    for handler in setup.at_exit:
        handler()

    assert setup.x11.keymap[200] == setup.x11.keymap[201] == [0] * 4


async def test_reused_keycode_waits_until_the_app_has_read_the_keymap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watch = FakeWatch(reads_after_polls=3)
    setup = ready_keyboard(monkeypatch, watch=watch)

    await setup.type_scan("éüß")

    assert watch.polls == 3
    assert setup.xtst.pressed == [201, 200, 201]  # ß takes é's keycode once the app caught up


async def test_no_wait_while_spare_keycodes_last(monkeypatch: pytest.MonkeyPatch) -> None:
    watch = FakeWatch(reads_after_polls=None)
    setup = ready_keyboard(monkeypatch, watch=watch)

    await setup.type_scan("éüé")

    assert watch.polls == 0


async def test_a_scan_waits_reuse_wait_s_at_most(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(x11, "REUSE_WAIT_S", 0.05)
    setup = ready_keyboard(monkeypatch, watch=FakeWatch(reads_after_polls=None))
    started = time.monotonic()

    await setup.type_scan("éüßçñ")  # three reuses, and the app never reads the keymap

    assert 0.05 <= time.monotonic() - started < 0.5
    assert len(setup.xtst.pressed) == 5


@pytest.mark.parametrize(
    ("watch", "focused"), [(None, APP_CLIENT), (FakeWatch(reads_after_polls=1), None)]
)
async def test_without_record_or_a_focused_app_reuse_waits_for_time(
    monkeypatch: pytest.MonkeyPatch, watch: FakeWatch | None, focused: int | None
) -> None:
    monkeypatch.setattr(x11, "REUSE_WAIT_S", 0.05)
    setup = ready_keyboard(monkeypatch, watch=watch, focused=focused)
    started = time.monotonic()

    await setup.type_scan("éüß")

    assert time.monotonic() - started >= 0.05  # until é was typed REUSE_WAIT_S ago
    assert setup.xtst.pressed == [201, 200, 201]


def test_keymap_watch_counts_reads_after_emupos_changes() -> None:
    watch = x11.KeymapWatch(OWN_CLIENT, xkb_opcode=135, poll=lambda: None)

    watch.note(OWN_CLIENT, FROM_CLIENT, 100, 0)  # emupos changes the keymap
    watch.note(APP_CLIENT, FROM_CLIENT, 101, 0)  # the app reads it: GetKeyboardMapping
    watch.note(OWN_CLIENT, FROM_CLIENT, 100, 0)
    assert watch.has_read(APP_CLIENT, 1)
    assert not watch.has_read(APP_CLIENT, 2)

    watch.note(APP_CLIENT, FROM_CLIENT, 135, 8)  # XkbGetMap
    assert watch.has_read(APP_CLIENT, 2)


def test_keymap_watch_ignores_other_requests() -> None:
    watch = x11.KeymapWatch(OWN_CLIENT, xkb_opcode=135, poll=lambda: None)

    watch.note(APP_CLIENT, FROM_CLIENT, 135, 9)  # another XKB request
    watch.note(APP_CLIENT, 0, 101, 0)  # not a request
    watch.note(OWN_CLIENT, FROM_CLIENT, 101, 0)  # emupos's own read
    watch.note(APP_CLIENT, FROM_CLIENT, 100, 0)  # another client's keymap change

    assert not watch.has_read(APP_CLIENT, 0)
    assert watch.changes == 0
    assert not watch.started
    watch.note(0, START_OF_DATA, 0, 0)
    assert watch.started


def killed_emupos(keysyms: list[int], alive: bool = False) -> Callable[[FakeX11], None]:
    """Another emupos bound keycode 201 to é; its key code 201 now holds `keysyms`."""

    def set_up(fake: FakeX11) -> None:
        fake.keymap[201] = keysyms
        atom = fake.atom(f"{x11.BINDINGS_PREFIX}other")
        fake.properties[atom] = [201, ord("é")]
        if alive:
            fake.owners[atom] = 0x300001

    return set_up


def test_keycodes_left_by_a_killed_emupos_are_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch, before=killed_emupos([ord("é")] * 2 + [0] * 2))

    assert setup.x11.keymap[201] == [0] * 4
    assert setup.x11.atom(f"{x11.BINDINGS_PREFIX}other") not in setup.x11.properties


def test_keycodes_of_a_running_emupos_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    bound = [ord("é")] * 2 + [0] * 2
    setup = ready_keyboard(monkeypatch, before=killed_emupos(bound, alive=True))

    assert setup.x11.keymap[201] == bound
    assert setup.x11.atom(f"{x11.BINDINGS_PREFIX}other") in setup.x11.properties


def test_keycode_changed_since_the_kill_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch, before=killed_emupos([F13, 0, F13, 0]))

    assert setup.x11.keymap[201] == [F13, 0, F13, 0]
    assert setup.x11.atom(f"{x11.BINDINGS_PREFIX}other") not in setup.x11.properties


def test_bindings_are_listed_until_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    setup = ready_keyboard(monkeypatch)

    setup.type("é")
    assert setup.x11.own_bindings() == [201, ord("é")]
    for handler in setup.at_exit:
        handler()

    assert setup.x11.own_bindings() is None
