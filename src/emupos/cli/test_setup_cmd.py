"""`emupos setup print-queue` on a pretend Windows: PowerShell and the API are replaced."""

import sys
from typing import Any

import pytest
from typer.testing import CliRunner

from emupos.cli.app import app
from emupos.cli.client import Client, SimulatorUnreachableError
from emupos.windows_queue import setup

runner = CliRunner()


def powershell(answer: dict[str, Any], scripts: list[str] | None = None) -> Any:
    def run(script: str) -> dict[str, Any]:
        if scripts is not None:
            scripts.append(script)
        return answer

    return run


FRONT: dict[str, Any] = {
    "id": "front",
    "type": "printer",
    "connections": [{"kind": "tcp", "endpoint": "127.0.0.1:9100"}],
}
# An id holding U+2019, which Windows PowerShell reads as a single quote: it would end the quoted
# queue name in the script this command builds (test_setup.py covers the other quote characters).
PWNED_ID = f"front{chr(0x2019)}; Write-Output pwned; {chr(0x2019)}"


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Pretend to be Windows; returns the PowerShell scripts that would have run."""
    scripts: list[str] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("EMUPOS_API", "http://127.0.0.1:1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(setup, "run_powershell", powershell({"ok": True, "changed": True}, scripts))
    return scripts


def api_answers(monkeypatch: pytest.MonkeyPatch, *devices: dict[str, Any]) -> None:
    def get(_client: Client, path: str) -> Any:
        return list(devices) if path == "/devices" else devices[0]

    monkeypatch.setattr(Client, "get", get)


def test_creates_the_queue_for_the_only_printer(
    windows: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api_answers(monkeypatch, FRONT)

    result = runner.invoke(app, ["setup", "print-queue"])

    assert result.exit_code == 0, result.output
    assert "emupos-front" in result.stdout
    assert "127.0.0.1:9100" in result.stdout
    assert "not delivered through a print queue" in result.stdout
    assert "$Name = 'emupos-front'\n$Port = 9100\n$Driver = 'Generic / Text Only'\n" in windows[0]


def test_printer_without_tcp_creates_nothing(
    windows: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api_answers(monkeypatch, FRONT | {"connections": [{"kind": "serial", "endpoint": "COM5"}]})

    result = runner.invoke(app, ["setup", "print-queue", "--device", "front"])

    assert result.exit_code == 1
    assert "a `tcp` connection must be added to `front` in `emupos.yaml`" in result.stderr
    assert windows == []


def test_simulator_not_running_exits_3(windows: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(client: Client, path: str) -> Any:
        raise SimulatorUnreachableError(client.base_url)

    monkeypatch.setattr(Client, "get", unreachable)

    result = runner.invoke(app, ["setup", "print-queue", "--device", "front"])

    assert result.exit_code == 3
    assert windows == []


def test_remove_with_device_needs_no_simulator(
    windows: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(client: Client, path: str) -> Any:
        raise SimulatorUnreachableError(client.base_url)

    monkeypatch.setattr(Client, "get", unreachable)

    result = runner.invoke(app, ["setup", "print-queue", "--device", "front", "--remove"])

    assert result.exit_code == 0, result.output
    assert "removed print queue emupos-front" in result.stdout
    assert "Remove-Printer -Name $Name" in windows[0]


def test_remove_with_an_id_that_is_not_a_device_id_is_a_usage_error(
    windows: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(client: Client, path: str) -> Any:
        raise SimulatorUnreachableError(client.base_url)

    monkeypatch.setattr(Client, "get", unreachable)

    result = runner.invoke(app, ["setup", "print-queue", "--remove", "--device", PWNED_ID])

    assert result.exit_code == 2  # not 3: the value is refused before the simulator is needed
    assert "is not a device id" in result.stderr
    assert windows == []


def test_an_api_that_answers_with_an_id_that_is_not_a_device_id_is_refused(
    windows: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # --api can name any server, so the ids it answers with are checked like a typed one.
    api_answers(monkeypatch, FRONT | {"id": PWNED_ID})

    result = runner.invoke(app, ["setup", "print-queue"])

    assert result.exit_code == 2
    assert "is not a device id" in result.stderr
    assert windows == []


def test_nothing_to_remove(monkeypatch: pytest.MonkeyPatch, windows: list[str]) -> None:
    monkeypatch.setattr(setup, "run_powershell", powershell({"ok": True, "changed": False}))

    result = runner.invoke(app, ["setup", "print-queue", "--device", "front", "--remove"])

    assert result.exit_code == 0
    assert "nothing to remove" in result.stdout


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            {
                "ok": False,
                "step": "Add-PrinterPort",
                "error_id": "HRESULT 0x80070005,Add-PrinterPort",
            },
            "Run as administrator",
        ),
        (
            {"ok": False, "step": "Print Spooler", "error_id": "spooler_stopped"},
            "Start-Service Spooler",
        ),
        (
            {"ok": False, "step": "Get-Printer", "error_id": "HRESULT 0x800706BA,Get-Printer"},
            "Start-Service Spooler",
        ),
        (
            {"ok": False, "step": "Add-Printer", "message": "The driver is missing.", "notes": []},
            "Add-Printer failed: The driver is missing.",
        ),
    ],
)
def test_windows_refusals_name_the_fix(
    windows: list[str], monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any], expected: str
) -> None:
    api_answers(monkeypatch, FRONT)
    monkeypatch.setattr(setup, "run_powershell", powershell(answer))

    result = runner.invoke(app, ["setup", "print-queue"])

    assert result.exit_code == 1
    assert expected in result.stderr
