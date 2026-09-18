"""`emupos doctor` (cli spec, "Doctor diagnostics")."""

import ipaddress
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

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
from emupos.transports.ports import tcp_port_free, udp_port_free
from emupos.transports.udp import exchange
from emupos.windows_queue import snmp

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
    windows = windows_facts(loaded) if sys.platform == "win32" else None
    checks = [check_python(), config_check, check_ports(loaded, windows), check_keyboard(loaded)]
    if sys.platform == "win32":
        checks += windows_checks(loaded, windows)
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


def check_ports(loaded: LoadedConfig | None, windows: "WindowsFacts | None" = None) -> Check:
    """The API port and every TCP port are free, or held by the simulator running this configuration."""
    api = loaded.config.api if loaded is not None else ApiSettings()
    running = _running_tcp_endpoints(api)
    wanted = [("the control API (`api.port`)", api.host, api.port)]
    for device in loaded.config.devices if loaded is not None else []:
        wanted += [(device.id, c.tcp.host, c.tcp.port) for c in device.connections if c.tcp]
    busy = [
        f"port {port} on {host} ({user}{_held_by(windows.tcp_owners.get(port) if windows else None)})"
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
    """macOS Accessibility, or X11 and libXtst on Linux: a failure only when this machine types.

    A `typed_by: client` scanner is typed wherever `emupos scan` runs, so a machine that only
    runs the simulator does not need a keyboard for it: a warning, not a failure.
    """
    needed = loaded is not None and any(
        isinstance(device, ScannerDevice)
        and device.mode == "keyboard"
        and device.typed_by == "server"
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


# --- Windows ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WindowsFacts:
    spooler: str  # the Print Spooler's status, e.g. "Running"; "" when it is not installed
    queues: list[str]  # emupos-* print queues
    com0com: list[tuple[str, str]]  # (device name, Windows problem code, e.g. CM_PROB_NONE)
    com_ports: list[str]
    snmp_owners: list[str]  # programs holding UDP port 161
    tcp_owners: dict[int, list[str]] = field(default_factory=dict[int, list[str]])


# Everything the Windows checks need, in one PowerShell run. Queues are read from the registry,
# which lists them even while the Print Spooler is stopped.
_WINDOWS_FACTS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
function Owners($endpoints) {
    $endpoints | ForEach-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)").Name } | Sort-Object -Unique
}
$tcp = @{}
foreach ($port in $TcpPorts) { $tcp["$port"] = @(Owners (Get-NetTCPConnection -State Listen -LocalPort $port)) }
@{
    spooler = "$((Get-Service -Name Spooler).Status)"
    queues = @(Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Print\Printers' | Where-Object { $_.PSChildName -like 'emupos-*' } | ForEach-Object { $_.PSChildName })
    com0com = @(Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like '*com0com*' } | ForEach-Object { @{ name = $_.FriendlyName; problem = "$($_.ConfigManagerErrorCode)" } })
    com_ports = @([System.IO.Ports.SerialPort]::GetPortNames())
    snmp_owners = @(Owners (Get-NetUDPEndpoint -LocalPort 161))
    tcp_owners = $tcp
} | ConvertTo-Json -Compress -Depth 4
"""


def windows_facts(loaded: LoadedConfig | None) -> WindowsFacts | None:
    """What Windows reports about spooler, queues, COM ports and port owners; None when it cannot say."""
    from emupos.windows_queue.setup import QueueSetupError, run_powershell

    ports = sorted(
        {c.tcp.port for d in loaded.config.devices for c in d.connections if c.tcp}
        | {loaded.config.api.port}
        if loaded is not None
        else {ApiSettings().port}
    )
    try:
        facts: Any = run_powershell(
            f"$TcpPorts = @({', '.join(map(str, ports))})\n{_WINDOWS_FACTS}"
        )
        return WindowsFacts(
            spooler=str(facts["spooler"]),
            queues=list(map(str, _listed(facts["queues"]))),
            com0com=[(str(d["name"]), str(d["problem"])) for d in _listed(facts["com0com"])],
            com_ports=[str(port).upper() for port in _listed(facts["com_ports"])],
            snmp_owners=list(map(str, _listed(facts["snmp_owners"]))),
            tcp_owners={
                int(port): list(map(str, _listed(names)))
                for port, names in facts["tcp_owners"].items()
            },
        )
    except (QueueSetupError, KeyError, TypeError, ValueError):
        return None


def _listed(value: Any) -> list[Any]:
    """A JSON list from PowerShell, which may send a one-item list as the item and an empty one as null."""
    if value is None:
        return []
    return [value] if isinstance(value, str | dict) else list(value)


def windows_checks(loaded: LoadedConfig | None, windows: WindowsFacts | None) -> list[Check]:
    if windows is None:
        return [
            Check(
                "windows",
                "warn",
                "COM port, print queue and SNMP checks could not run: Windows PowerShell did not answer",
                "check that `powershell.exe` starts in this terminal, then run `emupos doctor` again",
            )
        ]
    return [check_com_ports(loaded, windows), check_print_queues(windows), check_snmp_port(windows)]


def check_com_ports(loaded: LoadedConfig | None, windows: WindowsFacts) -> Check:
    """Configured COM ports exist; com0com is installed and its driver was not blocked."""
    wanted = [
        (c.serial.port, d.id)
        for d in (loaded.config.devices if loaded is not None else [])
        for c in d.connections
        if c.serial is not None and c.serial.port is not None
    ]
    missing = [
        f"{port} ({device})" for port, device in wanted if port.upper() not in windows.com_ports
    ]
    blocked = [
        name for name, problem in windows.com0com if problem in {"CM_PROB_UNSIGNED_DRIVER", "52"}
    ]
    note = (
        "; com0com is installed but Windows blocked its driver (Code 52, CM_PROB_UNSIGNED_DRIVER), "
        "because Secure Boot only loads drivers signed through Microsoft"
        if blocked
        else ""
    )
    options = (
        "see docs/windows-serial.md: turn Secure Boot off, use a signed virtual serial port "
        "driver, or use real serial hardware"
    )
    if missing:
        return Check(
            "com-ports",
            "fail",
            f"COM ports that do not exist: {', '.join(missing)}{note}",
            f"create the port or connect the adapter, or change `serial.port` in emupos.yaml; {options}",
        )
    if wanted:
        return Check("com-ports", "pass", f"COM ports exist: {', '.join(p for p, _ in wanted)}")
    if blocked:
        return Check("com-ports", "warn", f"no COM ports are configured{note}", options)
    if windows.com0com:
        return Check("com-ports", "pass", "com0com is installed")
    return Check(
        "com-ports",
        "warn",
        "no COM ports are configured and no com0com virtual port pair is installed; "
        "serial devices on Windows need an existing COM port",
        options,
    )


def check_print_queues(windows: WindowsFacts) -> Check:
    """The Print Spooler runs, and existing queues are reported as one-way."""
    queues = ", ".join(windows.queues)
    start = 'start it in a PowerShell opened with "Run as administrator": `Start-Service Spooler`'
    if windows.spooler != "Running":
        if windows.queues:
            return Check(
                "print-queue",
                "fail",
                f"the Print Spooler service is not running, so print queues {queues} cannot print",
                start,
            )
        return Check(
            "print-queue",
            "warn",
            "the Print Spooler service is not running; `emupos setup print-queue` needs it",
            start,
        )
    if not windows.queues:
        return Check("print-queue", "pass", "Print Spooler is running; no emupos print queues")
    return Check(
        "print-queue",
        "pass",
        f"print queues {queues}: these queues cannot deliver status replies; status testing "
        "requires connecting to the printer's TCP port or serial connection directly",
    )


def check_snmp_port(windows: WindowsFacts) -> Check:
    """UDP port 161 is free for, or held by, the simulator's SNMP responder."""
    if udp_port_free("127.0.0.1", snmp.PORT):
        return Check("snmp", "pass", "UDP port 161 is free for print queue status")
    request = snmp.Message(0, b"public", snmp.GET, 1, ((snmp.SYS_DESCR, snmp.NULL, b""),))
    reply = exchange("127.0.0.1", snmp.PORT, snmp.encode_message(request), timeout=1.0)
    try:
        if reply is not None and snmp.decode_message(reply).varbinds[0][2] == b"emupos":
            return Check("snmp", "pass", "UDP port 161 is held by the running simulator")
    except (ValueError, IndexError):
        pass
    return Check(
        "snmp",
        "fail" if windows.queues else "warn",
        snmp.PORT_IN_USE.replace(
            " is in use,", f" is in use{_held_by(windows.snmp_owners, ' (held by {})')},"
        ),
        snmp.STOP_SNMP_SERVICE,
    )


def _held_by(owners: list[str] | None, template: str = ", held by {}") -> str:
    return template.format(", ".join(owners)) if owners else ""
