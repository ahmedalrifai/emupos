"""`emupos config init | validate | schema` (configuration spec)."""

import json
from pathlib import Path
from typing import Annotated

import typer

from emupos.cli.output import CliError, console, table
from emupos.config import (
    DEFAULT_CONFIG_FILE,
    ConfigError,
    ConfigNotFoundError,
    LoadedConfig,
    ScannerDevice,
    find_config_file,
    json_schema,
    load_config_file,
    starter_config_text,
)

config_app = typer.Typer(
    help="Create, check and describe emupos.yaml. None of these need the simulator.",
    no_args_is_help=True,
)


def load(path: Path | None) -> LoadedConfig:
    """Find and validate the configuration like `emupos run` does, or raise CliError."""
    try:
        return load_config_file(find_config_file(path, Path.cwd()))
    except ConfigNotFoundError as error:
        raise CliError(
            f"no configuration file at {error.path}",
            "create one with `emupos config init`",
            code="config_not_found",
            exit_code=2,
        ) from None
    except ConfigError as error:
        raise CliError(invalid_message(error), code="invalid_config") from None
    except OSError as error:
        raise CliError(f"cannot read {path or DEFAULT_CONFIG_FILE}: {error.strerror}") from None


def invalid_message(error: ConfigError) -> str:
    count = len(error.issues)
    problems = "1 problem" if count == 1 else f"{count} problems"
    return f"{error.source} is not valid ({problems}):\n" + "\n".join(
        f"  {issue}" for issue in error.issues
    )


PathArgument = Annotated[
    Path | None,
    typer.Argument(
        help=f"Configuration file. Default: {DEFAULT_CONFIG_FILE} in the current directory.",
        show_default=False,
    ),
]


@config_app.command("init")
def init(path: PathArgument = None) -> None:
    """Write a commented starter configuration. An existing file is never overwritten."""
    target = path or Path(DEFAULT_CONFIG_FILE)
    try:
        with target.open("x", encoding="utf-8") as file:
            file.write(starter_config_text())
    except FileExistsError:
        raise CliError(
            f"{target} already exists and was left unchanged",
            "edit it, or write the starter somewhere else: `emupos config init other.yaml`",
        ) from None
    except OSError as error:
        raise CliError(f"cannot write {target}: {error.strerror}") from None
    out = console()
    out.print(f"Wrote {target}")
    out.print("Next: `emupos config validate`, then `emupos run`.")


@config_app.command("validate")
def validate(path: PathArgument = None) -> None:
    """Check a configuration file and list its devices. Opens no ports and needs no simulator."""
    loaded = load(path)
    out = console()
    out.print(f"{loaded.source} is valid")
    devices = table("DEVICE", "TYPE", "PROFILE")
    for device in loaded.config.devices:
        profile = f"{device.mode} mode" if isinstance(device, ScannerDevice) else device.profile
        devices.add_row(device.id, device.type, profile)
    out.print(devices)


@config_app.command("schema")
def schema() -> None:
    """Print the JSON Schema of emupos.yaml, for editor completion and validation."""
    typer.echo(json.dumps(json_schema(), indent=2))
