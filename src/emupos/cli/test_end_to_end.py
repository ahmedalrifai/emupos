"""`emupos run` in a subprocess, driven by the other commands (cli spec; tasks 12.8).

Posix only: the test stops the simulator with SIGINT, as Ctrl+C does, and uses a pty scale.
"""

import json
import os
import signal
import socket  # noqa: TID251 - the test plays the POS and connects to the printer port
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from emupos.cli import actions
from emupos.cli.app import app
from emupos.cli.client import Client
from emupos.cli.output import CliError
from emupos.scanner.keys import PhysicalKey
from emupos.transports.keyboard import keyboard as keyboard_module
from emupos.transports.keyboard.keyboard import KeyboardUnavailableError
from emupos.transports.keyboard.test_keyboard import FakeKeyboard
from emupos.transports.ports import tcp_port_free

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="uses SIGINT and a pty scale")

runner = CliRunner()
CONFIG = """\
schema: 1
api: {{ port: {api} }}
devices:
  - id: front
    type: printer
    profile: epson-tm-t20iii
    connections: [{{ tcp: {{ port: {front} }} }}]
  - id: kitchen
    type: printer
    profile: epson-tm-t20iii
    connections: [{{ tcp: {{ port: {kitchen} }} }}]
  - id: deli
    type: scale
    profile: toledo8217-15kg
    connections: [{{ serial: {{ pty: true, link: {link} }} }}]
  - id: lane1
    type: scanner
    mode: serial
    connections: [{{ tcp: {{ port: {lane1} }} }}]
  - id: lane2
    type: scanner
    mode: keyboard
  - id: lane3
    type: scanner
    mode: keyboard
    typed_by: client
"""


def free_ports(count: int) -> list[int]:
    return [port for port in range(46000, 47000) if tcp_port_free("127.0.0.1", port)][:count]


class Simulator:
    def __init__(self, process: subprocess.Popen[bytes], log: Path, api: str, ports: list[int]):
        self.process, self.log, self.api, self.ports = process, log, api, ports

    def cli(self, *args: str) -> "CliResult":
        result = runner.invoke(app, ["--api", self.api, *args])
        return CliResult(result.exit_code, result.stdout, result.stderr)

    def output(self) -> str:
        return self.log.read_text(encoding="utf-8")


class CliResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str) -> None:
        self.exit_code, self.stdout, self.stderr = exit_code, stdout, stderr

    def json(self) -> Any:
        return json.loads(self.stdout)


@pytest.fixture
def simulator(tmp_path: Path) -> Iterator[Simulator]:
    api, front, kitchen, lane1 = ports = free_ports(4)
    config = tmp_path / "emupos.yaml"
    link = f"emupos-test-{os.getpid()}"
    text = CONFIG.format(api=api, front=front, kitchen=kitchen, lane1=lane1, link=link)
    config.write_text(text, encoding="utf-8")
    log = tmp_path / "run.log"
    env = {
        key: value for key, value in os.environ.items() if key not in {"NO_COLOR", "FORCE_COLOR"}
    }
    env["TMPDIR"] = str(tmp_path)  # serial links go under tmp_path/emupos, never the user's TMPDIR
    with log.open("wb") as output:
        process = subprocess.Popen(  # noqa: S603 - runs this Python with fixed arguments
            [sys.executable, "-m", "emupos.cli.app", "run", "--config", str(config)],
            stdout=output,
            stderr=subprocess.STDOUT,
            cwd=tmp_path,
            env=env,
            # A shell that starts background jobs ignores SIGINT in them; Ctrl+C must work here.
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL),
        )
    running = Simulator(process, log, f"http://127.0.0.1:{api}", ports)
    try:
        wait_for_health(running)
        yield running
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def wait_for_health(simulator: Simulator) -> None:
    client = Client(simulator.api)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if simulator.process.poll() is not None:
            pytest.fail(f"emupos run exited early:\n{simulator.output()}")
        try:
            client.get("/health")
            return
        except CliError:
            time.sleep(0.1)
    pytest.fail(f"emupos run did not start:\n{simulator.output()}")


def wait_until(condition: Callable[[], object], message: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    pytest.fail(message)


def state(simulator: Simulator, device_id: str) -> Any:
    devices = simulator.cli("devices", "--json").json()
    return next(item["state"] for item in devices if item["id"] == device_id)


def test_simulator_session(simulator: Simulator, tmp_path: Path) -> None:
    listed = simulator.cli("devices", "--json")
    assert listed.exit_code == 0
    assert [item["id"] for item in listed.json()] == [
        "front",
        "kitchen",
        "deli",
        "lane1",
        "lane2",
        "lane3",
    ]
    plain = simulator.cli("devices")
    assert "kitchen" in plain.stdout
    assert "\x1b" not in plain.stdout

    # faults
    assert simulator.cli("fault", "set", "front", "paper-out").exit_code == 0
    assert state(simulator, "front")["faults"] == ["paper-out"]
    assert simulator.cli("fault", "clear", "front", "paper-out").exit_code == 0
    assert state(simulator, "front")["faults"] == []
    unknown = simulator.cli("fault", "set", "nope", "paper-out")
    assert unknown.exit_code == 1
    assert "nope" in unknown.stderr
    assert "fix: " in unknown.stderr

    # receipts; the job also opens the drawer (ESC p)
    empty = simulator.cli("receipt", "show", "--device", "front")
    assert empty.exit_code == 1
    assert "has no receipts yet" in empty.stderr
    with socket.create_connection(("127.0.0.1", simulator.ports[1])) as pos:
        pos.sendall(bytes.fromhex("1b 40 1b 70 00 19 fa 48 69 0a 1d 56 00"))
        wait_until(
            lambda: simulator.cli("receipt", "list", "--device", "front", "--json").json(),
            "the receipt did not complete",
        )
    saved = tmp_path / "receipt.png"
    shown = simulator.cli("receipt", "show", "--device", "front", "--save", str(saved))
    assert shown.exit_code == 0
    assert "Hi" in shown.stdout
    image = Client(simulator.api).send("GET", "/devices/front/receipts/latest/image")
    assert saved.read_bytes() == image
    assert "Hi" in simulator.cli("receipt", "show", "--device", "front", "--json").json()["text"]

    # the drawer, and device selection between two printers
    assert state(simulator, "front")["drawer"] == "open"
    ambiguous = simulator.cli("drawer", "close")
    assert ambiguous.exit_code == 2
    assert "front" in ambiguous.stderr
    assert "kitchen" in ambiguous.stderr
    assert simulator.cli("drawer", "close", "--device", "front").exit_code == 0
    assert state(simulator, "front")["drawer"] == "closed"

    # the only scale is inferred
    assert simulator.cli("scale", "set", "1.25kg").exit_code == 0
    assert state(simulator, "deli")["grams"] == 1250
    assert state(simulator, "deli")["stable"] is True
    assert simulator.cli("scale", "set", "800g", "--unstable", "--device", "deli").exit_code == 0
    assert state(simulator, "deli")["stable"] is False
    assert simulator.cli("scale", "zero", "--device", "front").exit_code == 1  # wrong type

    # a serial scanner needs no keyboard permission
    scanned = simulator.cli("scan", "2112345012506", "--device", "lane1", "--countdown", "0")
    assert scanned.exit_code == 0, scanned.stderr

    # Ctrl+C
    simulator.process.send_signal(signal.SIGINT)
    assert simulator.process.wait(timeout=15) == 0
    output = simulator.output()
    summary = [
        simulator.api,
        f"127.0.0.1:{simulator.ports[1]}",
        f"emupos/emupos-test-{os.getpid()} -> /dev/",
    ]
    events = [
        "printer.status.changed",
        "printer.job.completed",
        "drawer.closed",
        "scanner.scan.delivered",
    ]
    for expected in summary + events:
        assert expected in output
    assert "\x1b" not in output
    assert all(tcp_port_free("127.0.0.1", port) for port in simulator.ports)


def test_keyboard_scan_is_cancelled_while_this_terminal_has_focus(
    simulator: Simulator, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(actions, "terminal_with_focus", lambda: "Warp")

    cancelled = simulator.cli("scan", "6291041500213", "--device", "lane2", "--countdown", "0")

    assert cancelled.exit_code == 1
    assert "scan cancelled: Warp still has keyboard focus" in cancelled.stderr
    assert "click your POS window" in cancelled.stderr
    simulator.process.send_signal(signal.SIGINT)
    assert simulator.process.wait(timeout=15) == 0
    assert "scanner.scan" not in simulator.output()  # nothing was requested, so nothing typed


def test_invalid_keyboard_scan_is_refused_before_the_countdown(simulator: Simulator) -> None:
    started = time.monotonic()

    refused = simulator.cli("scan", "كود42", "--device", "lane2", "--countdown", "30")

    assert refused.exit_code == 1
    assert "unicode" in refused.stderr
    assert time.monotonic() - started < 10  # refused at once, not after the 30-second countdown


# --- client-typed scans (cli spec, "Scan command") -------------------------------------------


class NotReadyKeyboard(FakeKeyboard):
    def check_ready(self) -> None:
        raise KeyboardUnavailableError(
            "keystrokes cannot be typed: this is a Wayland session",
            "log in to an X11 session, or set `mode: serial` for this scanner",
        )


def use_keyboard(monkeypatch: pytest.MonkeyPatch, keyboard: FakeKeyboard) -> FakeKeyboard:
    """`emupos scan` runs in this process, so its keyboard is the one we hand it here."""
    monkeypatch.setattr(keyboard_module, "system_keyboard", lambda: keyboard)
    return keyboard


def test_client_typed_scan_is_typed_here_and_reported(
    simulator: Simulator, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyboard = use_keyboard(monkeypatch, FakeKeyboard())
    monkeypatch.setattr(actions, "terminal_with_focus", lambda: None)

    scanned = simulator.cli("scan", "Ab1", "--device", "lane3", "--countdown", "0")

    assert scanned.exit_code == 0, scanned.stderr
    assert "lane3 delivered Ab1" in scanned.stdout
    assert [key for _, key in keyboard.presses] == [
        PhysicalKey(0x04, shift=True),
        PhysicalKey(0x05),
        PhysicalKey(0x1E),
        PhysicalKey(0x28),
    ]
    assert "scanner.scan.delivered" in simulator.output()


def test_client_typed_scan_reports_keystrokes_the_system_refused(
    simulator: Simulator, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_keyboard(monkeypatch, FakeKeyboard(refuse=(PhysicalKey(0x28),)))  # Enter is discarded
    monkeypatch.setattr(actions, "terminal_with_focus", lambda: None)

    scanned = simulator.cli("scan", "Ab1", "--device", "lane3", "--countdown", "0")

    assert scanned.exit_code == 1
    assert "accepted 3 of 4 keystrokes" in scanned.stderr
    assert "higher privileges" in scanned.stderr
    assert "scanner.scan.delivered" not in simulator.output()
    # The scanner is free again: a scan this keyboard accepts in full now succeeds.
    use_keyboard(monkeypatch, FakeKeyboard())
    assert simulator.cli("scan", "1", "--device", "lane3", "--countdown", "0").exit_code == 0


def test_client_typed_scan_is_cancelled_while_this_terminal_has_focus(
    simulator: Simulator, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyboard = use_keyboard(monkeypatch, FakeKeyboard())
    monkeypatch.setattr(actions, "terminal_with_focus", lambda: "Warp")

    cancelled = simulator.cli("scan", "6291041500213", "--device", "lane3", "--countdown", "0")

    assert cancelled.exit_code == 1
    assert "scan cancelled: Warp still has keyboard focus" in cancelled.stderr
    assert keyboard.presses == []  # nothing typed, and nothing was requested either
    assert "scanner.scan" not in simulator.output()


def test_client_keyboard_not_ready_fails_before_the_countdown(
    simulator: Simulator, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_keyboard(monkeypatch, NotReadyKeyboard())
    started = time.monotonic()

    refused = simulator.cli("scan", "6291041500213", "--device", "lane3", "--countdown", "30")

    assert refused.exit_code == 1
    assert time.monotonic() - started < 5  # the 30-second countdown never ran
    assert "Wayland session" in refused.stderr
    assert "mode: serial" in refused.stderr
    assert "scanner.scan" not in simulator.output()


def test_devices_shows_who_types(simulator: Simulator) -> None:
    listed = simulator.cli("devices")

    assert "typed by the client" in listed.stdout
