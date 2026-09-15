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
