"""Run Odoo's Toledo 8217 scale driver against a simulated scale (weight-scale spec; design D8).

    uv run --with pyserial python scripts/odoo_toledo8217_conformance.py

macOS and Linux only (the scale is a pty). The script starts `emupos run` with one scale,
downloads Odoo's public driver files at a pinned commit into a temporary directory, and uses
them as a POS would: probe the port, then read the weight after each change a person makes at
the scale. Odoo is LGPL-3.0: its files are downloaded for this local run only and never copied
into this repository. The results are recorded in docs/protocols/toledo8217.md.

Exit status 0 when every check passes, 1 otherwise.
"""

import hashlib
import importlib.util
import json
import os
import queue
import socket  # noqa: TID251 - finds a free port for the control API
import subprocess
import sys
import tempfile
import threading
import time
import types
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NamedTuple

ODOO_COMMIT = "60b50790b9190be96db739ef3904303138db618f"  # odoo/odoo 19.0, March 2026
DRIVERS = "odoo.addons.iot_drivers.iot_handlers.drivers"
ODOO_FILES = {  # module name -> SHA-256 of the file at ODOO_COMMIT
    f"{DRIVERS}.serial_base_driver": "9958376da3fe6008e12d551a6da402b4d827038fb58708a62e6b3276eae82f39",
    f"{DRIVERS}.serial_scale_driver": "88934d95a1083aad4877edcdf271ee6c95004c9df917aebe5beb4333b7effa7f",
}
SCALE = "deli"


class Check(NamedTuple):
    name: str
    passed: bool
    detail: str = ""


CONFIG = """\
schema: 1
api: {{ port: {port} }}
devices:
  - id: deli
    type: scale
    profile: toledo8217-15kg
    connections: [{{ serial: {{ pty: true }} }}]
"""


def main() -> int:
    if sys.platform == "win32":
        print("this check needs a pty scale: run it on macOS or Linux")
        return 1
    with tempfile.TemporaryDirectory() as workdir, simulator(Path(workdir)) as (api, link, log):
        odoo = load_odoo_driver(Path(workdir))
        checks = run_checks(odoo, api, str(link))
        mismatch = "framing mismatch" in log.read_text(encoding="utf-8")
        checks.append(Check("Odoo opens the port as 9600 7E1: no framing warning", not mismatch))
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}  {name}{f'  ({detail})' if detail else ''}")
    failed = sum(not passed for _, passed, _ in checks)
    print(f"\nOdoo {ODOO_COMMIT[:10]}: {len(checks) - failed} passed, {failed} failed")
    return 1 if failed else 0


# --- the simulator ----------------------------------------------------------------------------


@contextmanager
def simulator(workdir: Path) -> Iterator[tuple[Callable[..., None], Path, Path]]:
    """Start `emupos run` with one Toledo scale; yield an API caller, the port path and the log."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = workdir / "emupos.yaml"
    config.write_text(CONFIG.format(port=port), encoding="utf-8")
    log = workdir / "run.log"
    env = {**os.environ, "TMPDIR": str(workdir)}  # the port link goes under workdir/emupos
    with log.open("wb") as output:
        process = subprocess.Popen(  # noqa: S603 - this Python with fixed arguments
            [sys.executable, "-m", "emupos.cli.app", "run", "--config", str(config)],
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
        )
    base = f"http://127.0.0.1:{port}/api/v1"

    def call(method: str, path: str, body: dict[str, Any] | None = None) -> None:
        request = urllib.request.Request(  # noqa: S310 - fixed localhost URL
            base + path,
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(request, timeout=5).close()  # noqa: S310

    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                call("GET", "/health")
                break
            except OSError:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise SystemExit(f"emupos run did not start:\n{log.read_text()}") from None
                time.sleep(0.2)
        yield call, workdir / "emupos" / SCALE, log
    finally:
        process.terminate()
        process.wait(timeout=10)


# --- Odoo's driver ----------------------------------------------------------------------------


def load_odoo_driver(workdir: Path) -> types.ModuleType:
    """Import Odoo's scale driver with the rest of Odoo (web server, IoT box) replaced by stubs."""
    stub_odoo_imports()
    for name, sha256 in ODOO_FILES.items():
        url = f"https://raw.githubusercontent.com/odoo/odoo/{ODOO_COMMIT}/addons/iot_drivers/iot_handlers/drivers/{name.rsplit('.', 1)[1]}.py"
        with urllib.request.urlopen(url, timeout=30) as response:
            source = response.read()
        if hashlib.sha256(source).hexdigest() != sha256:
            raise SystemExit(f"{url} does not match its pinned SHA-256")
        path = workdir / f"{name}.py"
        path.write_bytes(source)
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise SystemExit(f"cannot import {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # serial_scale_driver imports serial_base_driver by this name
        spec.loader.exec_module(module)
    return sys.modules[f"{DRIVERS}.serial_scale_driver"]


class EventManager:
    """Stands in for the IoT box's event manager: keeps what the driver pushes to the POS."""

    def __init__(self) -> None:
        self.pushed: queue.Queue[Any] = queue.Queue()

    def device_changed(self, device: Any, data: Any = None) -> None:
        self.pushed.put(device.data.get("result"))


event_manager = EventManager()


class Driver(threading.Thread):
    """The attributes Odoo's `iot_drivers.driver.Driver.__init__` sets, without the IoT box."""

    def __init__(self, identifier: str, device: dict[str, str]) -> None:
        super().__init__(daemon=True)
        self.dev = device
        self.device_identifier = identifier
        self.device_name = ""
        self.device_connection = ""
        self.device_type = ""
        self.device_manufacturer = ""
        self.data: dict[str, Any] = {"value": "", "result": ""}
        self._actions: dict[str, Callable[..., Any]] = {}
        self._stopped = threading.Event()


def stub_odoo_imports() -> None:
    http = types.SimpleNamespace(Controller=object, route=lambda *_a, **_k: lambda f: f)
    stubs = {
        "odoo": {"http": http},
        "odoo.addons": {},
        "odoo.addons.iot_drivers": {},
        "odoo.addons.iot_drivers.controllers": {},
        "odoo.addons.iot_drivers.controllers.proxy": {"proxy_drivers": {}},
        "odoo.addons.iot_drivers.event_manager": {"event_manager": event_manager},
        "odoo.addons.iot_drivers.driver": {"Driver": Driver},
        "odoo.addons.iot_drivers.iot_handlers": {},
        DRIVERS: {},
    }
    for name, attributes in stubs.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        sys.modules[name] = module


# --- the checks -------------------------------------------------------------------------------


def run_checks(odoo: types.ModuleType, api: Callable[..., None], link: str) -> list[Check]:
    checks: list[Check] = []
    device = {"identifier": link}

    def weigh(grams: int, *, stable: bool = True) -> None:
        api("PUT", f"/devices/{SCALE}/weight", {"grams": grams, "stable": stable})

    probed = odoo.Toledo8217Driver.supported(device)
    checks.append(Check("probe: Odoo recognises the port as a Toledo 8217 scale", probed))
    driver = odoo.Toledo8217Driver(link, device)

    def read_once(name: str, expected: float, *, tare_mode: bool | None = None) -> None:
        """The POS's `read_once` action. Only weight replies update `tare_mode`."""
        driver.data["result"] = None  # a reply Odoo cannot parse leaves this untouched
        driver.action({"action": "read_once"})
        result = driver.data["result"]
        passed = result == expected and type(result) is type(expected)  # 0 error, 0.0 weight
        passed = passed and tare_mode in (None, driver.tare_mode)
        checks.append(Check(name, passed, f"result {result!r}, tare_mode {driver.tare_mode}"))

    # An action uses the connection the IoT box keeps open for the device.
    with odoo.serial_connection(link, odoo.Toledo8217Protocol) as connection:
        driver._connection = connection
        weigh(1250)
        read_once("stable 1250 g reads 1.25 kg", 1.25, tare_mode=False)
        weigh(1253)
        read_once("1253 g on a 5 g division reads 1.255 kg", 1.255)
        weigh(15000)
        read_once("15000 g, exactly at capacity, reads 15.0 kg", 15.0)
        weigh(0)
        read_once("an empty scale reads 0.0 kg, a weight", 0.0)
        weigh(200)
        api("POST", f"/devices/{SCALE}/tare")
        weigh(1450)
        read_once("tare 200 g, gross 1450 g reads 1.25 kg in tare mode", 1.25, tare_mode=True)
        weigh(100)
        read_once("tare 200 g, gross 100 g (net below zero) reads 0, an error", 0)
        api("POST", f"/devices/{SCALE}/zero")
        weigh(16000)
        read_once("16000 g, over capacity, reads 0, an error", 0)
        weigh(-100)
        read_once("-100 g, under zero, reads 0, an error", 0)
        weigh(1250, stable=False)
        read_once("unstable 1250 g reads 0, an error, while in motion", 0)
        time.sleep(0.6)  # the profile settles after 500 ms
        read_once("the same weight after settling reads 1.25 kg", 1.25, tare_mode=False)

    # The IoT box's reading loop pushes every new weight to the POS.
    while not event_manager.pushed.empty():
        event_manager.pushed.get()
    weigh(2500)
    driver.start()
    first = wait_for(event_manager.pushed, 2.5)
    weigh(3000)
    second = wait_for(event_manager.pushed, 3.0)
    driver._stopped.set()
    driver.join(timeout=5)
    detail = f"pushed {first!r}, then {second!r}"
    checks.append(
        Check("the reading loop pushes each new weight", (first, second) == (2.5, 3.0), detail)
    )
    return checks


def wait_for(pushed: queue.Queue[Any], value: float, timeout: float = 5) -> Any:
    """The first pushed value equal to `value`, or the last one seen when it never arrives."""
    deadline, last = time.monotonic() + timeout, None
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            last = pushed.get(timeout=remaining)
        except queue.Empty:
            break
        if last == value:
            break
    return last


if __name__ == "__main__":
    sys.exit(main())
