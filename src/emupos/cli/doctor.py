"""`emupos doctor` (cli spec, "Doctor diagnostics")."""

import ipaddress
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import typer
from rich.text import Text

from emupos.cli.client import Client
from emupos.cli.config_cmd import invalid_message
from emupos.cli.devices import JsonOption
from emupos.cli.output import CliError, console, print_json, use_json
from emupos.config import (
    ApiSettings,
    ConfigError,
    ConfigNotFoundError,
    LoadedConfig,
    ScannerDevice,
    find_config_file,
    load_config_file,
)
from emupos.transports.ports import tcp_port_free

MINIMUM_PYTHON = (3, 13)
SYMBOLS = {"pass": ("✓", "green"), "warn": ("!", "yellow"), "fail": ("✗", "red")}


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    status: Literal["pass", "warn", "fail"]
    message: str
    fix: str | None = None


def doctor(ctx: typer.Context, json_output: JsonOption = False) -> None:
    """Check this machine and ./emupos.yaml for everything the simulator needs."""
    use_json(ctx, json_output)
    loaded, config_check = check_config(Path.cwd())
    checks = [check_python(), config_check, check_ports(loaded), check_keyboard(loaded)]
    if sys.platform == "win32":
        checks += windows_placeholders()
    ok = all(check.status != "fail" for check in checks)
    if json_output:
        print_json({"ok": ok, "checks": [asdict(check) for check in checks]})
    else:
        out = console()
        for check in checks:
            symbol, style = SYMBOLS[check.status]
            out.print(Text.assemble((symbol, f"bold {style}"), " ", check.message))
            if check.fix and check.status != "pass":
                out.print(f"  fix: {check.fix}")
    if not ok:
        raise typer.Exit(1)


def check_python() -> Check:
    current = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info >= MINIMUM_PYTHON:
        return Check("python", "pass", f"Python {current}")
    return Check(
        "python",
        "fail",
        f"Python {current} is too old; emupos needs Python 3.13 or newer",
        "install with `uv tool install emupos`, which downloads a suitable Python",
    )


def check_config(cwd: Path) -> tuple[LoadedConfig | None, Check]:
    try:
        path = find_config_file(None, cwd)
        return load_config_file(path), Check("config", "pass", f"{path} is valid")
    except ConfigNotFoundError as error:
        message = f"no configuration file at {error.path}; checked the default API port only"
        return None, Check("config", "warn", message, "create one with `emupos config init`")
    except ConfigError as error:
        fix = "correct the entries listed; `emupos config validate` checks the file again"
        return None, Check("config", "fail", invalid_message(error), fix)
    except OSError as error:
        return None, Check(
            "config",
            "fail",
            f"cannot read the configuration: {error}",
            "check the file's permissions",
        )


def check_ports(loaded: LoadedConfig | None) -> Check:
    """The API port and every TCP port are free, or held by the simulator running this configuration."""
    api = loaded.config.api if loaded is not None else ApiSettings()
    running = _running_tcp_endpoints(api)
    wanted = [("the control API (`api.port`)", api.host, api.port)]
    for device in loaded.config.devices if loaded is not None else []:
        wanted += [(device.id, c.tcp.host, c.tcp.port) for c in device.connections if c.tcp]
    busy = [
        f"port {port} on {host} ({user})"
        for index, (user, host, port) in enumerate(wanted)
        if not (running is not None and (index == 0 or f"{host}:{port}" in running))
        and not tcp_port_free(host, port)
    ]
    ports = ", ".join(str(port) for _, _, port in wanted)
    if busy:
        return Check(
            "ports",
            "fail",
            f"in use by another program: {'; '.join(busy)}",
            "stop the program using the port, or choose another port in emupos.yaml",
        )
    held = " or held by the running simulator" if running is not None else ""
    return Check("ports", "pass", f"TCP ports free{held}: {ports}")


def _running_tcp_endpoints(api: ApiSettings) -> set[str] | None:
    """TCP endpoints of the emupos simulator answering on the API port, or None when none answers."""
    host = api.host.strip("[]")
    try:
        if ipaddress.ip_address(host).is_unspecified:
            host = "127.0.0.1" if host == "0.0.0.0" else "::1"  # noqa: S104 (comparison, not a bind)
    except ValueError:
        pass  # a host name such as localhost
    client = Client(f"http://[{host}]:{api.port}" if ":" in host else f"http://{host}:{api.port}")
    try:
        client.get("/health")
        devices = client.get("/devices")
    except CliError:
        return None
    return {c["endpoint"] for d in devices for c in d["connections"] if c["kind"] == "tcp"}


def check_keyboard(loaded: LoadedConfig | None) -> Check:
    """macOS Accessibility, or X11 and libXtst on Linux: a failure only when a keyboard scanner is configured."""
    needed = loaded is not None and any(
        isinstance(device, ScannerDevice) and device.mode == "keyboard"
        for device in loaded.config.devices
    )
    try:
        from emupos.transports.keyboard.keyboard import KeyboardUnavailableError, system_keyboard
    except ImportError as error:
        return Check(
            "keyboard",
            "warn",
            f"keyboard-mode scanning could not be checked: {error}",
            "reinstall emupos: `uv tool install --reinstall emupos`",
        )
    try:
        system_keyboard().check_ready()
    except KeyboardUnavailableError as error:
        return Check("keyboard", "fail" if needed else "warn", error.message, error.fix)
    return Check("keyboard", "pass", "keyboard-mode scanners can type into the focused window")


def windows_placeholders() -> list[Check]:
    return [
        Check(
            "com0com",
            "warn",
            "com0com and COM ports: not checked yet (pending Windows serial work)",
            "check the com0com port pair in Device Manager",
        ),
        Check(
            "print-queue",
            "warn",
            "print queue and SNMP checks: not available yet",
            "connect the POS to the printer's TCP port directly",
        ),
    ]
