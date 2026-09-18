"""Loading and validating `emupos.yaml` and device profiles.

Validation happens in two passes so that every problem is reported together:
1. structure — Pydantic models (types, required keys, unknown keys, value ranges);
2. semantics — rules spanning several fields or the environment (duplicate ids, ports and
   links, profile existence and type, operating-system support).
"""

import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import ErrorDetails

SUPPORTED_SCHEMA = 1
DEFAULT_CONFIG_FILE = "emupos.yaml"
DEVICE_TYPES = ("printer", "scale", "scanner")

# ---------------------------------------------------------------------------------------------
# Errors


@dataclass(frozen=True, slots=True)
class ConfigIssue:
    path: str  # e.g. "devices[1].connections[0].tcp.port"; "" for file-level problems
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}" if self.path else self.message


class ConfigError(Exception):
    """The configuration (or a profile it uses) is invalid. Carries every issue found."""

    def __init__(self, source: str, issues: Sequence[ConfigIssue]) -> None:
        self.source = source
        self.issues = tuple(issues)
        super().__init__(f"{source}: " + "; ".join(str(issue) for issue in self.issues))


class ConfigNotFoundError(Exception):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"no configuration file at {path} (create one with `emupos config init`)")


# ---------------------------------------------------------------------------------------------
# Models shared by configuration and profiles


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


Port = Annotated[int, Field(ge=1, le=65535)]
Level = Literal["high", "low"]


class SerialFraming(_StrictModel):
    baud: Annotated[int, Field(ge=50)]
    data_bits: Literal[5, 6, 7, 8]
    parity: Literal["none", "even", "odd"]
    stop_bits: Literal[1, 2]


# ---------------------------------------------------------------------------------------------
# Device profiles


class FontCell(_StrictModel):
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]


class PrinterProfile(_StrictModel):
    type: Literal["printer"]
    name: str
    dpi: Annotated[int, Field(ge=1)]
    width_dots: Annotated[int, Field(ge=1)]
    font_a: FontCell
    font_b: FontCell
    code_pages: dict[int, str]  # ESC t number -> code page name, e.g. 37: PC864
    default_code_page: int
    drawer_sensor_open_level: Level
    serial: SerialFraming | None = None

    @model_validator(mode="after")
    def _default_code_page_is_mapped(self) -> Self:
        if self.default_code_page not in self.code_pages:
            raise ValueError(f"default_code_page {self.default_code_page} is not in code_pages")
        return self


class ScaleProfile(_StrictModel):
    type: Literal["scale"]
    name: str
    protocol: Literal["toledo8217"]
    capacity_grams: Annotated[int, Field(ge=1)]
    division_grams: Annotated[int, Field(ge=1)]
    reply_integer_digits: Annotated[int, Field(ge=1)]
    reply_decimals: Annotated[int, Field(ge=0)]
    settle_ms: Annotated[int, Field(ge=0)]
    serial: SerialFraming


type Profile = PrinterProfile | ScaleProfile

# ---------------------------------------------------------------------------------------------
# Configuration file

DeviceId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]
LinkName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]


class TcpEndpoint(_StrictModel):
    host: str = "127.0.0.1"
    port: Port


class SerialEndpoint(_StrictModel):
    pty: Literal[True] | None = None
    port: str | None = None
    link: LinkName | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        if (self.pty is None) == (self.port is None):
            raise ValueError("a serial entry needs exactly one of `pty: true` or `port`")
        if self.link is not None and self.pty is None:
            raise ValueError("`link` is only allowed together with `pty: true`")
        if self.link is not None and self.link.endswith(".pid"):
            raise ValueError(
                "a `link` name must not end in `.pid`; emupos uses that name for its own files"
            )
        return self


class Connection(_StrictModel):
    tcp: TcpEndpoint | None = None
    serial: SerialEndpoint | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        if (self.tcp is None) == (self.serial is None):
            raise ValueError("each connection entry needs exactly one of `tcp` or `serial`")
        return self


class DrawerSettings(_StrictModel):
    sensor_open_level: Level | None = None


class PrinterDevice(_StrictModel):
    id: DeviceId
    type: Literal["printer"]
    profile: str
    connections: Annotated[list[Connection], Field(min_length=1)]
    job_idle_timeout_ms: Annotated[int, Field(ge=1)] = 2000
    receipts_dir: str = "./receipts"
    drawer: DrawerSettings = DrawerSettings()


class ScaleDevice(_StrictModel):
    id: DeviceId
    type: Literal["scale"]
    profile: str
    connections: Annotated[list[Connection], Field(min_length=1)]


class ScannerDevice(_StrictModel):
    id: DeviceId
    type: Literal["scanner"]
    mode: Literal["keyboard", "serial"]
    suffix: Literal["enter", "tab", "none"] = "enter"
    inter_key_delay_ms: Annotated[int, Field(ge=0)] = 10
    typed_by: Literal["server", "client"] = "server"
    connections: list[Connection] = []

    @field_validator("typed_by")
    @classmethod
    def _typed_by_needs_keyboard(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("mode") == "serial":
            raise ValueError(
                "a serial scanner writes bytes and types no keys, so it has no `typed_by`"
            )
        return value

    @field_validator("connections")
    @classmethod
    def _connections_match_mode(
        cls, value: list[Connection], info: ValidationInfo
    ) -> list[Connection]:
        mode = info.data.get("mode")
        if mode == "keyboard" and value:
            raise ValueError(
                "a keyboard scanner types into the focused window and has no connections"
            )
        if mode == "serial" and not value:
            raise ValueError("a serial scanner needs at least one connection")
        return value


type Device = PrinterDevice | ScaleDevice | ScannerDevice


class ApiSettings(_StrictModel):
    host: str = "127.0.0.1"
    port: Port = 8765


class Config(_StrictModel):
    schema_version: Annotated[int, Field(alias="schema", ge=1)]
    api: ApiSettings = ApiSettings()
    devices: Annotated[
        list[Annotated[PrinterDevice | ScaleDevice | ScannerDevice, Field(discriminator="type")]],
        Field(min_length=1),
    ]


def json_schema() -> dict[str, Any]:
    """JSON Schema for `emupos.yaml`, for editor completion and validation."""
    schema = Config.model_json_schema(by_alias=True)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **schema,
        "title": f"emupos configuration (schema {SUPPORTED_SCHEMA})",
    }


# ---------------------------------------------------------------------------------------------
# Loaded configuration


@dataclass(frozen=True, slots=True)
class LoadedConfig:
    config: Config
    source: str  # file path, or "built-in demo configuration"
    base_dir: Path  # relative paths in the file resolve against this directory
    profiles: Mapping[str, Profile]  # by device id, for printers and scales

    def printer_profile(self, device_id: str) -> PrinterProfile:
        profile = self.profiles[device_id]
        if not isinstance(profile, PrinterProfile):
            raise TypeError(f"device {device_id} has no printer profile")
        return profile

    def scale_profile(self, device_id: str) -> ScaleProfile:
        profile = self.profiles[device_id]
        if not isinstance(profile, ScaleProfile):
            raise TypeError(f"device {device_id} has no scale profile")
        return profile

    def receipts_dir(self, device: PrinterDevice) -> Path:
        return (self.base_dir / device.receipts_dir).resolve()

    def drawer_sensor_open_level(self, device: PrinterDevice) -> Level:
        return (
            device.drawer.sensor_open_level
            or self.printer_profile(device.id).drawer_sensor_open_level
        )


def find_config_file(explicit: Path | None, cwd: Path) -> Path:
    path = explicit if explicit is not None else cwd / DEFAULT_CONFIG_FILE
    if not path.is_file():
        raise ConfigNotFoundError(path)
    return path


def load_config_file(path: Path, platform: str = sys.platform) -> LoadedConfig:
    return parse_config(path.read_text(encoding="utf-8"), str(path), path.parent, platform)


def parse_config(
    text: str, source: str, base_dir: Path, platform: str = sys.platform
) -> LoadedConfig:
    raw = _load_yaml(text, source)
    _check_schema_version(raw, source)
    try:
        config = Config.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(source, _issues_from(error)) from None
    profiles, issues = _resolve_profiles(config, base_dir)
    issues += _semantic_issues(config, profiles, platform)
    if issues:
        raise ConfigError(source, issues)
    return LoadedConfig(config, source, base_dir, profiles)


def starter_config_text() -> str:
    return resources.files("emupos").joinpath("starter.yaml").read_text(encoding="utf-8")


def demo_config(platform: str = sys.platform, cwd: Path | None = None) -> LoadedConfig:
    """Built-in configuration that runs on every OS without external prerequisites."""
    devices: list[dict[str, object]] = [
        {
            "id": "front",
            "type": "printer",
            "profile": "epson-tm-t20iii",
            "connections": [{"tcp": {"port": 9100}}],
        },
        {"id": "lane1", "type": "scanner", "mode": "keyboard"},
    ]
    if platform != "win32":
        devices.append(
            {
                "id": "deli",
                "type": "scale",
                "profile": "toledo8217-15kg",
                "connections": [{"serial": {"pty": True}}],
            }
        )
    text = yaml.safe_dump({"schema": SUPPORTED_SCHEMA, "devices": devices})
    return parse_config(text, "built-in demo configuration", cwd or Path.cwd(), platform)


# ---------------------------------------------------------------------------------------------
# Internals


def _load_yaml(text: str, source: str) -> object:
    try:
        # safe_load reads plain data only: tags such as !!python/object are rejected, never constructed.
        return yaml.safe_load(text)
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        where = f"line {mark.line + 1}, column {mark.column + 1}: " if mark else ""
        raise ConfigError(source, [ConfigIssue("", f"{where}{error.problem or error}")]) from None
    except yaml.YAMLError as error:
        raise ConfigError(source, [ConfigIssue("", f"not valid YAML: {error}")]) from None


def _check_schema_version(raw: object, source: str) -> None:
    if not isinstance(raw, dict):
        return
    version = raw.get("schema")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if isinstance(version, int) and not isinstance(version, bool) and version > SUPPORTED_SCHEMA:
        message = (
            f"this file uses schema {version}, but this emupos supports up to schema {SUPPORTED_SCHEMA}; "
            "upgrade emupos to read it"
        )
        raise ConfigError(source, [ConfigIssue("schema", message)])


def _issues_from(error: ValidationError) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    for detail in error.errors():
        path = _format_path(detail["loc"])
        if detail["type"] in {"union_tag_invalid", "union_tag_not_found"}:
            path += ".type"  # Pydantic reports a bad `type` at the device, not the key
        issues.append(ConfigIssue(path, _friendly_message(detail)))
    return issues


def _format_path(loc: tuple[int | str, ...]) -> str:
    path = ""
    previous: int | str | None = None
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        elif isinstance(previous, int) and part in DEVICE_TYPES:
            pass  # discriminated-union tag inserted by Pydantic, not a key in the file
        elif part in {"function-after", "tagged-union"}:
            pass
        else:
            path += f".{part}" if path else str(part)
        previous = part
    return path


def _friendly_message(detail: ErrorDetails) -> str:
    kind = detail["type"]
    context = detail.get("ctx") or {}
    field = str(detail["loc"][-1]) if detail["loc"] else ""
    if kind == "extra_forbidden":
        return "unknown key"
    if kind == "missing":
        return "required key is missing"
    if kind in {"int_type", "int_parsing"}:
        return "an integer is required"
    if kind in {"greater_than_equal", "less_than_equal"} and field == "port":
        return "a port from 1 to 65535 is expected"
    if kind in {"union_tag_invalid", "union_tag_not_found"}:
        tag = context.get("tag")
        message = "`type` must be one of printer, scale or scanner"
        if tag == "drawer":
            message += "; a cash drawer is not a device — configure it with the `drawer` key of its printer"
        return message
    if kind == "value_error":
        return str(context.get("error", detail["msg"]))
    return detail["msg"]


def _builtin_profile_names(kind: str) -> list[str]:
    folder = resources.files("emupos").joinpath("profiles", f"{kind}s")
    return sorted(
        entry.name.removesuffix(".yaml")
        for entry in folder.iterdir()
        if entry.name.endswith(".yaml")
    )


def _is_profile_path(reference: str) -> bool:
    return "/" in reference or "\\" in reference or reference.endswith((".yaml", ".yml"))


def _resolve_profiles(
    config: Config, base_dir: Path
) -> tuple[dict[str, Profile], list[ConfigIssue]]:
    profiles: dict[str, Profile] = {}
    issues: list[ConfigIssue] = []
    for index, device in enumerate(config.devices):
        if isinstance(device, ScannerDevice):
            continue
        path = f"devices[{index}].profile"
        try:
            profile = _load_profile(device.profile, device.type, base_dir)
        except ConfigError as error:
            issues += [ConfigIssue(path, f"{error.source}: {issue}") for issue in error.issues]
            continue
        except _ProfileLookupError as error:
            issues.append(ConfigIssue(path, str(error)))
            continue
        if profile.type != device.type:
            issues.append(
                ConfigIssue(
                    path,
                    f"`{device.profile}` is a {profile.type} profile, not a {device.type} profile",
                )
            )
            continue
        profiles[device.id] = profile
    return profiles, issues


class _ProfileLookupError(Exception):
    pass


def _load_profile(reference: str, device_type: str, base_dir: Path) -> Profile:
    if _is_profile_path(reference):
        file = base_dir / reference
        if not file.is_file():
            raise _ProfileLookupError(f"profile file `{reference}` does not exist")
        text, source = file.read_text(encoding="utf-8"), reference
    else:
        for kind in DEVICE_TYPES[:2]:
            if reference in _builtin_profile_names(kind):
                folder = resources.files("emupos").joinpath("profiles", f"{kind}s")
                text, source = (
                    folder.joinpath(f"{reference}.yaml").read_text(encoding="utf-8"),
                    reference,
                )
                break
        else:
            names = ", ".join(_builtin_profile_names(device_type))
            raise _ProfileLookupError(
                f"unknown profile `{reference}`; built-in {device_type} profiles: {names}"
            )
    return _parse_profile(text, source)


def _parse_profile(text: str, source: str) -> Profile:
    raw = _load_yaml(text, source)
    kind = raw.get("type") if isinstance(raw, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    model = ScaleProfile if kind == "scale" else PrinterProfile
    try:
        return model.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(source, _issues_from(error)) from None


def _semantic_issues(
    config: Config, profiles: Mapping[str, Profile], platform: str
) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    issues += _duplicate_issues(
        ((f"devices[{i}].id", device.id) for i, device in enumerate(config.devices)),
        lambda value, first: f"`{value}` is already used by {first.removesuffix('.id')}",
    )
    tcp_paths: list[tuple[str, tuple[str, int]]] = []
    link_paths: list[tuple[str, str]] = []
    for i, device in enumerate(config.devices):
        profile = profiles.get(device.id)
        for j, connection in enumerate(device.connections):
            base = f"devices[{i}].connections[{j}]"
            if connection.tcp is not None:
                tcp_paths.append((f"{base}.tcp.port", (connection.tcp.host, connection.tcp.port)))
                if connection.tcp.port == config.api.port:
                    issues.append(
                        ConfigIssue(
                            f"{base}.tcp.port",
                            f"port {connection.tcp.port} is used by the control API (`api.port`)",
                        )
                    )
            if connection.serial is not None:
                if connection.serial.pty:
                    link_paths.append((f"{base}.serial.link", connection.serial.link or device.id))
                    if platform == "win32":
                        issues.append(
                            ConfigIssue(
                                f"{base}.serial",
                                "`pty: true` is not supported on Windows; use `serial: { port: COMx }` "
                                "with one end of a com0com virtual port pair (see docs/windows-serial.md)",
                            )
                        )
                if (
                    isinstance(device, PrinterDevice | ScaleDevice)
                    and profile is not None
                    and profile.serial is None
                ):
                    issues.append(
                        ConfigIssue(
                            f"{base}.serial",
                            f"profile `{device.profile}` defines no serial framing",
                        )
                    )
    issues += _duplicate_issues(
        tcp_paths,
        lambda value, first: f"port {value[1]} on {value[0]} is already used by {first}",
    )
    issues += _duplicate_issues(
        link_paths,
        lambda value, first: f"link `{value}` is already used by {first}",
    )
    return issues


def _duplicate_issues[T](
    entries: Iterable[tuple[str, T]], message: Callable[[T, str], str]
) -> list[ConfigIssue]:
    first_path: dict[T, str] = {}
    issues: list[ConfigIssue] = []
    for path, value in entries:
        if value in first_path:
            issues.append(ConfigIssue(path, message(value, first_path[value])))
        else:
            first_path[value] = path
    return issues
