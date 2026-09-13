"""X11 keyboard checks with the environment and library loader replaced; no X server needed."""

import pytest

from emupos.scanner.keys import ENTER, LEFT_SHIFT, TAB, US_LAYOUT, PhysicalKey
from emupos.transports.keyboard import x11
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError


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
