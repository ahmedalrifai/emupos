"""macOS keyboard tests. Nothing is ever posted: CGEventPost is replaced by a recorder."""

import sys
from typing import Any

import pytest

from emupos.scanner.keys import ENTER, TAB, US_LAYOUT, PhysicalKey, UnicodeText
from emupos.transports.keyboard import macos
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Quartz exists on macOS only")


@pytest.fixture
def quartz() -> Any:
    if sys.platform != "darwin":  # also tells type checkers for other platforms
        pytest.skip("Quartz exists on macOS only")
    return macos.Quartz


@pytest.fixture
def posted(monkeypatch: pytest.MonkeyPatch, quartz: Any) -> list[Any]:
    events: list[Any] = []

    def record(_tap: int, event: Any) -> None:
        events.append(event)

    monkeypatch.setattr(quartz, "CGEventPost", record)
    assert quartz.CGEventPost is record  # never post real keystrokes from a test
    return events


def describe(quartz: Any, event: Any) -> tuple[int, str, bool]:
    code = quartz.CGEventGetIntegerValueField(event, quartz.kCGKeyboardEventKeycode)
    kind = {
        quartz.kCGEventKeyDown: "down",
        quartz.kCGEventKeyUp: "up",
        quartz.kCGEventFlagsChanged: "flags",  # what macOS makes of a modifier key event
    }[quartz.CGEventGetType(event)]
    shift = bool(quartz.CGEventGetFlags(event) & quartz.kCGEventFlagMaskShift)
    return code, kind, shift


# Accessibility permission


def test_trusted(monkeypatch: pytest.MonkeyPatch, quartz: Any) -> None:
    monkeypatch.setattr(quartz, "CGPreflightPostEventAccess", lambda: True)

    macos.MacKeyboard().check_ready()


def test_not_trusted_names_the_settings_path_and_app(
    monkeypatch: pytest.MonkeyPatch, quartz: Any
) -> None:
    monkeypatch.setattr(quartz, "CGPreflightPostEventAccess", lambda: False)
    monkeypatch.setattr(
        macos, "_app_to_allow", lambda: "Terminal (/System/Applications/Utilities/Terminal.app)"
    )

    with pytest.raises(KeyboardUnavailableError) as caught:
        macos.MacKeyboard().check_ready()

    assert "cannot be posted" in caught.value.message
    assert "System Settings > Privacy & Security > Accessibility" in caught.value.fix
    assert "turn on Terminal (/System/Applications/Utilities/Terminal.app)" in caught.value.fix


def test_permission_granted_while_running(monkeypatch: pytest.MonkeyPatch, quartz: Any) -> None:
    trusted = False
    monkeypatch.setattr(quartz, "CGPreflightPostEventAccess", lambda: trusted)
    keyboard = macos.MacKeyboard()
    with pytest.raises(KeyboardUnavailableError):
        keyboard.check_ready()

    trusted = True

    keyboard.check_ready()


def test_app_to_allow_is_named() -> None:
    assert macos._app_to_allow()  # pyright: ignore[reportPrivateUsage]


# Key codes


def test_key_codes_type_the_us_characters(quartz: Any) -> None:
    def typed(code: int) -> str:
        event = quartz.CGEventCreateKeyboardEvent(None, code, True)  # created, never posted
        return quartz.CGEventKeyboardGetUnicodeString(event, 4, None, None)[1]

    if typed(0x00) != "a":
        pytest.skip("the current input source is not US or ABC")
    unshifted = {char: key for char, key in US_LAYOUT.items() if not key.shift}
    assert {char: typed(macos.KEY_CODES[key.usage]) for char, key in unshifted.items()} == {
        char: char for char in unshifted
    }
    assert typed(macos.KEY_CODES[ENTER]) == "\r"
    assert typed(macos.KEY_CODES[TAB]) == "\t"


def test_shifted_key_is_wrapped_in_shift(posted: list[Any], quartz: Any) -> None:
    assert macos.MacKeyboard().press(PhysicalKey(0x04, shift=True))

    assert [describe(quartz, event) for event in posted] == [
        (0x38, "flags", True),
        (0x00, "down", True),
        (0x00, "up", True),
        (0x38, "flags", False),
    ]


def test_plain_key(posted: list[Any], quartz: Any) -> None:
    assert macos.MacKeyboard().press(PhysicalKey(0x2D))

    assert [describe(quartz, event) for event in posted] == [
        (0x1B, "down", False),
        (0x1B, "up", False),
    ]


def test_unicode_text_is_attached(posted: list[Any], quartz: Any) -> None:
    assert macos.MacKeyboard().press(UnicodeText("ك"))

    assert [
        quartz.CGEventKeyboardGetUnicodeString(event, 4, None, None)[1] for event in posted
    ] == ["ك", "ك"]


def test_unknown_usage_refused(posted: list[Any]) -> None:
    assert not macos.MacKeyboard().press(PhysicalKey(0x3A))  # F1 is not a scanner key
    assert posted == []
