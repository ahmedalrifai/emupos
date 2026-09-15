"""The Windows checks of `emupos doctor`, from made-up Windows facts: no PowerShell needed."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from emupos.cli import doctor
from emupos.cli.app import app
from emupos.cli.doctor import WindowsFacts, check_com_ports, check_print_queues, check_snmp_port
from emupos.config import LoadedConfig, parse_config
from emupos.transports.keyboard import keyboard
from emupos.windows_queue import setup, snmp

BLOCKED = (
    "com0com - bus for serial port pair emulator 0 (COM# <-> COM#)",
    "CM_PROB_UNSIGNED_DRIVER",
)


def facts(**changes: Any) -> WindowsFacts:
    defaults: dict[str, Any] = {
        "spooler": "Running",
        "queues": [],
        "com0com": [],
        "com_ports": ["COM1"],
        "snmp_owners": [],
    }
    return WindowsFacts(**(defaults | changes))


def port_taken(monkeypatch: pytest.MonkeyPatch, reply: bytes | None) -> None:
    """UDP port 161 cannot be bound, and a probe of it gets `reply`."""

    def bindable(host: str, port: int) -> bool:
        return False

    def exchange(host: str, port: int, packet: bytes, timeout: float) -> bytes | None:
        return reply

    monkeypatch.setattr(doctor, "udp_port_free", bindable)
    monkeypatch.setattr(doctor, "exchange", exchange)


def deli_on(tmp_path: Path, port: str) -> LoadedConfig:
    text = f"""
schema: 1
devices:
  - {{ id: deli, type: scale, profile: toledo8217-15kg, connections: [ {{ serial: {{ port: {port} }} }} ] }}
"""
    return parse_config(text, "emupos.yaml", tmp_path, "win32")


def test_missing_com_port_with_blocked_com0com_fails(tmp_path: Path) -> None:
    check = check_com_ports(deli_on(tmp_path, "COM5"), facts(com0com=[BLOCKED]))

    assert check.status == "fail"
    assert "COM5 (deli)" in check.message
    assert "CM_PROB_UNSIGNED_DRIVER" in check.message
    assert "Secure Boot" in check.message
    assert check.fix is not None
    assert "docs/windows-serial.md" in check.fix


def test_existing_com_port_passes(tmp_path: Path) -> None:
    assert check_com_ports(deli_on(tmp_path, "com1"), facts()).status == "pass"


def test_blocked_com0com_is_a_warning_when_no_com_port_is_used() -> None:
    check = check_com_ports(None, facts(com0com=[BLOCKED]))

    assert check.status == "warn"
    assert "Secure Boot" in check.message


def test_existing_queue_is_reported_as_one_way() -> None:
    check = check_print_queues(facts(queues=["emupos-front"]))

    assert check.status == "pass"
    assert "emupos-front" in check.message
    assert "cannot deliver status replies" in check.message
    assert "TCP port or serial connection" in check.message


@pytest.mark.parametrize(("queues", "status"), [(["emupos-front"], "fail"), ([], "warn")])
def test_stopped_spooler(queues: list[str], status: str) -> None:
    check = check_print_queues(facts(spooler="Stopped", queues=queues))

    assert check.status == status
    assert check.fix is not None
    assert "Start-Service Spooler" in check.fix


@pytest.mark.parametrize(("queues", "status"), [(["emupos-front"], "fail"), ([], "warn")])
def test_snmp_port_taken_by_another_program(
    monkeypatch: pytest.MonkeyPatch, queues: list[str], status: str
) -> None:
    port_taken(monkeypatch, None)

    check = check_snmp_port(facts(queues=queues, snmp_owners=["snmp.exe"]))

    assert check.status == status
    assert '"SNMP Service"' in check.message
    assert "snmp.exe" in check.message
    assert check.fix is not None
    assert "Stop-Service SNMP" in check.fix


def test_snmp_port_held_by_the_simulator(monkeypatch: pytest.MonkeyPatch) -> None:
    reply = snmp.encode_message(
        snmp.Message(
            0, b"public", snmp.RESPONSE, 1, ((snmp.SYS_DESCR, snmp.OCTET_STRING, b"emupos"),)
        )
    )
    port_taken(monkeypatch, reply)

    assert check_snmp_port(facts(queues=["emupos-front"])).status == "pass"


def test_powershell_lists_are_read_even_when_unrolled(monkeypatch: pytest.MonkeyPatch) -> None:
    answer: dict[str, Any] = {
        "spooler": "Running",
        "queues": "emupos-front",
        "com0com": {"name": BLOCKED[0], "problem": BLOCKED[1]},
        "com_ports": None,
        "snmp_owners": [],
        "tcp_owners": {"8765": "lghub_updater.exe"},
    }

    def run(script: str) -> Any:
        assert "$TcpPorts = @(8765)" in script
        return answer

    monkeypatch.setattr(setup, "run_powershell", run)

    assert doctor.windows_facts(None) == WindowsFacts(
        "Running", ["emupos-front"], [BLOCKED], [], [], {8765: ["lghub_updater.exe"]}
    )


class FakeKeyboard:
    def check_ready(self) -> None:
        pass


def test_doctor_fails_on_windows_when_a_queue_cannot_get_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")
    queue = facts(queues=["emupos-front"])

    def windows_facts(loaded: LoadedConfig | None) -> WindowsFacts:
        return queue

    monkeypatch.setattr(doctor, "windows_facts", windows_facts)
    monkeypatch.setattr(keyboard, "system_keyboard", FakeKeyboard)
    port_taken(monkeypatch, None)

    result = CliRunner().invoke(app, ["doctor", "--json"])

    checks = {check["id"]: check for check in json.loads(result.stdout)["checks"]}
    assert result.exit_code == 1
    assert checks["snmp"]["status"] == "fail"
    assert "cannot deliver status replies" in checks["print-queue"]["message"]
