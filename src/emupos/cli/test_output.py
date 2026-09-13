"""Output modes, `emupos doctor`, and the event lines of `emupos run`."""

import io
import json
import logging
import socket  # noqa: TID251 - a test listener that occupies a port
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emupos.cli.app import app
from emupos.cli.event_lines import EventLines
from emupos.cli.output import console
from emupos.cli.run import ConsoleHandler
from emupos.events import Event, EventType, PublishedEvent
from emupos.transports.keyboard import keyboard

runner = CliRunner()

PRINTER_ON = """\
schema: 1
api: {{ port: {api_port} }}
devices:
  - id: front
    type: printer
    profile: epson-tm-t20iii
    connections: [{{ tcp: {{ port: {port} }} }}]
"""
KEYBOARD_SCANNER = "  - id: lane1\n    type: scanner\n    mode: keyboard\n"


@pytest.fixture(autouse=True)
def in_empty_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("EMUPOS_API", "NO_COLOR", "FORCE_COLOR"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def listener() -> Iterator[socket.socket]:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        yield server


def unused_port() -> int:
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        return spare.getsockname()[1]


def write_config(tmp_path: Path, port: int, extra: str = "") -> None:
    text = PRINTER_ON.format(api_port=unused_port(), port=port) + extra
    (tmp_path / "emupos.yaml").write_text(text, encoding="utf-8")


def validate_output(env: dict[str, str]) -> str:
    runner.invoke(app, ["config", "init"])
    result = runner.invoke(app, ["config", "validate"], env=env)
    assert result.exit_code == 0
    return result.stdout


def test_terminal_output_is_styled() -> None:
    assert "\x1b[" in validate_output({"FORCE_COLOR": "1"})


def test_piped_output_is_plain() -> None:
    output = validate_output({})
    assert "front" in output
    assert "\x1b" not in output


def test_no_color_in_a_terminal() -> None:
    assert "\x1b" not in validate_output({"FORCE_COLOR": "1", "NO_COLOR": "1"})


def test_doctor_json_report(tmp_path: Path) -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    report = json.loads(result.stdout)
    assert result.exit_code == (0 if report["ok"] else 1)
    assert {check["id"] for check in report["checks"]} >= {"python", "config", "ports", "keyboard"}
    for check in report["checks"]:
        assert set(check) == {"id", "status", "message", "fix"}
        assert check["status"] in {"pass", "warn", "fail"}
        if check["status"] != "pass":
            assert check["fix"]


def test_doctor_port_in_use_by_another_program(tmp_path: Path, listener: socket.socket) -> None:
    port = listener.getsockname()[1]
    write_config(tmp_path, port)
    result = runner.invoke(app, ["doctor", "--json"])
    ports = next(check for check in json.loads(result.stdout)["checks"] if check["id"] == "ports")
    assert ports["status"] == "fail"
    assert f"port {port}" in ports["message"]
    assert result.exit_code == 1


class _NoKeyboard:
    def check_ready(self) -> None:
        raise keyboard.KeyboardUnavailableError("keystrokes cannot be posted", "install libXtst")


@pytest.mark.parametrize(("extra", "status"), [(KEYBOARD_SCANNER, "fail"), ("", "warn")])
def test_doctor_keyboard_is_a_failure_only_when_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: str, status: str
) -> None:
    monkeypatch.setattr(keyboard, "system_keyboard", _NoKeyboard)
    write_config(tmp_path, unused_port(), extra)
    result = runner.invoke(app, ["doctor"])
    checks = json.loads(runner.invoke(app, ["doctor", "--json"]).stdout)["checks"]
    check = next(check for check in checks if check["id"] == "keyboard")
    assert (check["status"], check["fix"]) == (status, "install libXtst")
    assert "install libXtst" in result.stdout


def published(kind: EventType, device_id: str, **data: object) -> PublishedEvent:
    return PublishedEvent(Event(kind, device_id, data), datetime(2026, 9, 13, 12, 0, 1, tzinfo=UTC))


def test_event_lines() -> None:
    lines = EventLines(["front", "deli", "lane1"])
    job = published(EventType.PRINTER_JOB_COMPLETED, "front", receipt_id="r1", boundary="cut")
    assert lines.line(job).plain.endswith("job 1 · cut → r1")
    assert lines.line(job).plain.endswith("job 2 · cut → r1")
    expected = [
        (published(EventType.DRAWER_OPENED, "front", pin=2), "drawer opened (pin 2)"),
        (published(EventType.DRAWER_CLOSED, "front"), "drawer closed"),
        (
            published(
                EventType.SCALE_WEIGHT_CHANGED,
                "deli",
                grams=1250,
                tare_grams=0,
                net_grams=1250,
                stable=True,
            ),
            "1.250 kg stable",
        ),
        (
            published(
                EventType.SCALE_WEIGHT_CHANGED,
                "deli",
                grams=-100,
                tare_grams=200,
                net_grams=-300,
                stable=False,
            ),
            "-0.100 kg in motion (tare 0.200 kg, net -0.300 kg)",
        ),
        (
            published(EventType.SCANNER_SCAN_DELIVERED, "lane1", id="s1", data="2112345012506"),
            "scan delivered 2112345012506",
        ),
        (
            published(EventType.PRINTER_STATUS_CHANGED, "front", faults=["cover-open"]),
            "faults: cover-open",
        ),
        (published(EventType.PRINTER_STATUS_CHANGED, "front", faults=[]), "no faults"),
    ]
    for event, summary in expected:
        line = lines.line(event).plain
        assert event.event.device_id in line
        assert event.event.type in line
        assert line.endswith(summary)


def test_warnings_are_shown_distinctly() -> None:
    out = console()
    out.file = io.StringIO()
    handler = ConsoleHandler(out)
    record = logging.LogRecord(
        "emupos", logging.WARNING, "", 0, "deli: serial framing mismatch", (), None
    )
    handler.handle(record)
    assert out.file.getvalue() == "warning: deli: serial framing mismatch\n"


def test_run_api_port_in_use(tmp_path: Path, listener: socket.socket) -> None:
    port = listener.getsockname()[1]
    config = PRINTER_ON.format(api_port=port, port=unused_port())
    (tmp_path / "emupos.yaml").write_text(config, encoding="utf-8")
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 1
    assert f"port {port}" in result.stderr
