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
    ui: Annotated[
        bool,
        typer.Option(
            "--ui", help="Also serve the control page, a web page for the physical actions."
        ),
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
        serve(loaded, lambda simulator: _started(out, simulator, demo, ui), ui=ui)
    except StartupError as error:
        raise CliError(str(error), code="startup_failed") from None
    finally:
        logger.removeHandler(handler)
    out.print("emupos stopped")


def _started(out: Console, simulator: "Simulator", demo: bool, ui: bool) -> None:
    loaded = simulator.loaded
    title = "built-in demo configuration" if demo else loaded.source
    out.print(Text.assemble((f"emupos {version('emupos')}", "bold"), f" · {title}"))
    devices = table("DEVICE", "TYPE", "PROFILE", "CONNECTIONS")
    for device_id in simulator.device_ids():
        runtime = simulator.runtime(device_id)
        device = runtime.config
        if isinstance(device, ScannerDevice):
            profile = f"{device.mode} mode"
            fallback = (
                "typed by whoever runs `emupos scan`"
                if device.typed_by == "client"
                else "types into the focused window"
            )
        else:
            profile, fallback = device.profile, "-"
        endpoints = "\n".join(_endpoint_text(endpoint) for endpoint in runtime.endpoints)
        devices.add_row(device_id, device.type, profile, endpoints or fallback)
    out.print(devices)
    api = loaded.config.api
    host = f"[{api.host}]" if ":" in api.host else api.host
    out.print(Text.assemble(("control API ", "bold"), f"http://{host}:{api.port}"))
    if ui:
        url, problem = control_page(api.host, api.port)
        out.print(Text.assemble(("control page ", "bold"), url))
        if problem:
            warning(out, problem)
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


def control_page(host: str, port: int) -> tuple[str, str | None]:
    """Where the control page can act, and why it cannot when that is so (design D8).

    The page's requests are accepted only through a loopback address; a wildcard address listens
    on loopback too, so its URL names 127.0.0.1.
    """
    bare = host.strip("[]")
    if bare in {"0.0.0.0", "::"}:  # noqa: S104 - recognising the wildcard, not binding to it
        return f"http://127.0.0.1:{port}/", None
    url = f"http://[{bare}]:{port}/" if ":" in bare else f"http://{bare}:{port}/"
    if _is_loopback(host):
        return url, None
    problem = (
        f"a control page opened through {host} can show the devices but cannot act on them: "
        "it acts only through 127.0.0.1, localhost or [::1]; set api.host to 127.0.0.1 to use it"
    )
    return url, problem


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
