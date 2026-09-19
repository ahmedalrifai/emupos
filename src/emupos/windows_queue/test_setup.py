import re

import pytest

from emupos.windows_queue import setup

INPUTS = {"name", "port", "driver"}  # the values `_run` assigns before a script


@pytest.mark.parametrize("script", [setup._PRELUDE + setup._CREATE, setup._PRELUDE + setup._REMOVE])  # pyright: ignore[reportPrivateUsage]
def test_script_variables_never_overwrite_an_input(script: str) -> None:
    # PowerShell variable names ignore case, so `$port = ...` replaces the `$Port` passed in.
    assigned = re.findall(r"\$(\w+)\s*=[^=]|foreach\s*\(\$(\w+)\s+in", script, re.IGNORECASE)
    names = {name.lower() for pair in assigned for name in pair if name}

    assert names.isdisjoint(INPUTS)


def test_inputs_are_quoted_for_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    scripts: list[str] = []

    def run(script: str) -> dict[str, object]:
        scripts.append(script)
        return {"ok": True, "changed": True}

    monkeypatch.setattr(setup, "run_powershell", run)

    setup.create_queue("front", 9200)

    assert scripts[0].startswith(
        "$Name = 'emupos-front'\n$Port = 9200\n$Driver = 'Generic / Text Only'\n"
    )


# Windows PowerShell reads U+2018 to U+201B as single quotes as well as `'`, so doubling `'` is not
# enough to keep an arbitrary id inside a quoted name. Ids of another shape are refused instead.
# Written as code points because that is what the test is about (and they are ambiguous to read).
POWERSHELL_QUOTES = ("'", *map(chr, range(0x2018, 0x201C)))


@pytest.mark.parametrize(
    "device_id",
    [f"x{quote}; Write-Output pwned; {quote}" for quote in POWERSHELL_QUOTES]
    + ["front\nWrite-Output pwned", "front front", "Front", "-front", ""],
)
def test_an_id_that_is_not_a_device_id_never_reaches_powershell(
    device_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(setup, "run_powershell", powershell_that_must_not_run)

    for call in (
        lambda: setup.create_queue(device_id, 9200),
        lambda: setup.remove_queue(device_id),
    ):
        with pytest.raises(setup.QueueSetupError, match="is not a device id"):
            call()


def powershell_that_must_not_run(script: str) -> dict[str, object]:
    raise AssertionError(f"PowerShell was asked to run:\n{script}")
