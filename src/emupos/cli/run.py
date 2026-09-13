"""`emupos run` (cli spec, "Run command")."""

import ipaddress
import logging
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.text import Text

from emupos.cli.config_cmd import load
from emupos.cli.event_lines import EventLines
from emupos.cli.output import CliError, console, table, warning
from emupos.config import ScannerDevice, demo_config

if TYPE_CHECKING:
    from emupos.daemon.runtime import Endpoint
    from emupos.daemon.simulator import Simulator


def run(
    config: Annotated[
        Path | None,
        typer.Option(
            metavar="PATH",
            help="Configuration file. Default: emupos.yaml in the current directory.",
            show_default=False,
        ),
    ] = None,
    demo: Annotated[
        bool,
        typer.Option("--demo", help="Use the built-in demo devices instead of a file."),
    ] = False,
) -> None:
    """Start the simulated devices and the control API, and show events live. Ctrl+C stops."""
    if demo and config is not None:
        raise CliError(
            "--demo and --config are mutually exclusive",
            "use --demo for the built-in devices, or --config PATH for your own file",
            code="usage_error",
            exit_code=2,
        )
    loaded = demo_config() if demo else load(config)
    # imported here: the daemon loads the web server, which other commands skip
    from emupos.daemon.runtime import StartupError
    from emupos.daemon.server import serve

    out = console()
    handler = ConsoleHandler(out)
    logger = logging.getLogger("emupos")
    logger.addHandler(handler)
    try:
        serve(loaded, lambda simulator: _started(out, simulator, demo))
    except StartupError as error:
        raise CliError(str(error), code="startup_failed") from None
    finally:
        logger.removeHandler(handler)
    out.print("emupos stopped")


def _started(out: Console, simulator: "Simulator", demo: bool) -> None:
    loaded = simulator.loaded
    title = "built-in demo configuration" if demo else loaded.source
    out.print(Text.assemble((f"emupos {version('emupos')}", "bold"), f" · {title}"))
    devices = table("DEVICE", "TYPE", "PROFILE", "CONNECTIONS")
    for device_id in simulator.device_ids():
        runtime = simulator.runtime(device_id)
        device = runtime.config
        if isinstance(device, ScannerDevice):
            profile = f"{device.mode} mode"
            fallback = "types into the focused window"
        else:
            profile, fallback = device.profile, "-"
        endpoints = "\n".join(_endpoint_text(endpoint) for endpoint in runtime.endpoints)
        devices.add_row(device_id, device.type, profile, endpoints or fallback)
    out.print(devices)
    api = loaded.config.api
    host = f"[{api.host}]" if ":" in api.host else api.host
    out.print(Text.assemble(("control API ", "bold"), f"http://{host}:{api.port}"))
    if demo:
        out.print("Running the demo configuration. Write your own with `emupos config init`.")
    if not _is_loopback(api.host):
        warning(
            out,
            f"the control API listens on {api.host} and has no authentication: "
            "any machine that can reach this address can control the devices",
        )
    out.print("Showing events as they happen. Press Ctrl+C to stop.", style="dim")
    lines = EventLines(simulator.device_ids())
    for event in simulator.startup_events:  # published while connections opened, before this ran
        out.print(lines.line(event))
    simulator.bus.subscribe(lambda event: out.print(lines.line(event)))


def _endpoint_text(endpoint: "Endpoint") -> str:
    text = f"{endpoint.kind} {endpoint.endpoint}"
    if endpoint.device_path:
        text += f" -> {endpoint.device_path}"
    return text


def _is_loopback(host: str) -> bool:
    try:
        return host == "localhost" or ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


class ConsoleHandler(logging.Handler):
    """Shows log records from emupos (framing mismatches, lost keystrokes) among the events."""

    def __init__(self, out: Console) -> None:
        super().__init__(logging.WARNING)
        self.out = out

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            self.out.print(Text.assemble(("error: ", "bold red"), self.format(record)))
        else:
            warning(self.out, self.format(record))
