from pathlib import Path

import jsonschema
import pytest
import yaml

from emupos.config import (
    ConfigError,
    ConfigNotFoundError,
    PrinterDevice,
    demo_config,
    find_config_file,
    json_schema,
    load_config_file,
    parse_config,
    starter_config_text,
)

PRINTER = "{ id: front, type: printer, profile: epson-tm-t20iii, connections: [ { tcp: { port: 9100 } } ] }"


def parse(text: str, platform: str = "darwin", base_dir: Path = Path("/work/pos")):
    return parse_config(text, "emupos.yaml", base_dir, platform)


def issues_of(text: str, platform: str = "darwin") -> dict[str, str]:
    with pytest.raises(ConfigError) as error:
        parse(text, platform)
    return {issue.path: issue.message for issue in error.value.issues}


# --- discovery -----------------------------------------------------------------------------


def test_explicit_path_is_used(tmp_path: Path) -> None:
    file = tmp_path / "lane1.yaml"
    file.write_text(f"schema: 1\ndevices: [ {PRINTER} ]\n")

    assert find_config_file(file, cwd=Path("/elsewhere")) == file


def test_default_file_in_working_directory(tmp_path: Path) -> None:
    (tmp_path / "emupos.yaml").write_text(f"schema: 1\ndevices: [ {PRINTER} ]\n")

    assert find_config_file(None, cwd=tmp_path) == tmp_path / "emupos.yaml"


def test_missing_file_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(ConfigNotFoundError) as error:
        find_config_file(None, cwd=tmp_path)

    assert error.value.path == tmp_path / "emupos.yaml"
    assert "emupos config init" in str(error.value)


# --- schema version ------------------------------------------------------------------------


def test_newer_schema_asks_for_upgrade() -> None:
    issues = issues_of(f"schema: 2\ndevices: [ {PRINTER} ]\n")

    assert "schema 2" in issues["schema"]
    assert "up to schema 1" in issues["schema"]
    assert "upgrade" in issues["schema"]


def test_missing_schema() -> None:
    assert "schema" in issues_of(f"devices: [ {PRINTER} ]\n")


def test_schema_given_as_text() -> None:
    issues = issues_of(f'schema: "1"\ndevices: [ {PRINTER} ]\n')

    assert issues["schema"] == "an integer is required"


# --- validation paths ----------------------------------------------------------------------


def test_out_of_range_port_has_exact_path() -> None:
    text = f"""
schema: 1
devices:
  - {PRINTER}
  - {{ id: back, type: printer, profile: epson-tm-t20iii, connections: [ {{ tcp: {{ port: 70000 }} }} ] }}
"""
    issues = issues_of(text)

    assert issues["devices[1].connections[0].tcp.port"] == "a port from 1 to 65535 is expected"


def test_all_errors_are_reported_together() -> None:
    text = """
schema: 1
devices:
  - { id: front, type: drawer }
  - { id: back, type: printer, profile: epson-tm-t20iii, connections: [ { tcp: { port: 0 } } ] }
"""
    issues = issues_of(text)

    assert "devices[0].type" in issues
    assert "devices[1].connections[0].tcp.port" in issues


def test_malformed_yaml_names_line_and_column() -> None:
    text = "schema: 1\ndevices:\n  - id: front\n    type: printer\n   profile: bad-indent\n"

    with pytest.raises(ConfigError) as error:
        parse(text)

    assert "line 5" in str(error.value)
    assert "column" in str(error.value)


def test_object_tags_are_rejected_without_running_code(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    text = f"schema: !!python/object/apply:os.system ['touch {marker}']\ndevices: [ {PRINTER} ]\n"

    with pytest.raises(ConfigError) as error:
        parse(text)

    assert "python/object/apply:os.system" in str(error.value)
    assert not marker.exists()


def test_unknown_device_key() -> None:
    text = "schema: 1\ndevices: [ { id: front, type: printer, profile: epson-tm-t20iii, conections: [] } ]\n"

    assert issues_of(text)["devices[0].conections"] == "unknown key"


def test_unknown_nested_key() -> None:
    text = f"schema: 1\napi: {{ hots: 127.0.0.1 }}\ndevices: [ {PRINTER} ]\n"

    assert issues_of(text)["api.hots"] == "unknown key"


# --- devices and connections ---------------------------------------------------------------


def test_duplicate_device_id() -> None:
    text = (
        f"schema: 1\ndevices:\n  - {PRINTER}\n  - {{ id: front, type: scanner, mode: keyboard }}\n"
    )

    assert issues_of(text)["devices[1].id"] == "`front` is already used by devices[0]"


def test_drawer_declared_as_device() -> None:
    message = issues_of("schema: 1\ndevices: [ { id: till, type: drawer } ]\n")["devices[0].type"]

    assert "printer, scale or scanner" in message
    assert "`drawer` key of its printer" in message


def test_profile_of_wrong_device_type() -> None:
    text = "schema: 1\ndevices: [ { id: front, type: printer, profile: toledo8217-15kg, connections: [ { tcp: { port: 9100 } } ] } ]\n"

    assert "is a scale profile" in issues_of(text)["devices[0].profile"]


def test_keyboard_scanner_with_connections() -> None:
    text = "schema: 1\ndevices: [ { id: lane1, type: scanner, mode: keyboard, connections: [ { tcp: { port: 4000 } } ] } ]\n"

    assert "devices[0].connections" in issues_of(text)


def test_connection_with_both_kinds() -> None:
    text = "schema: 1\ndevices: [ { id: front, type: printer, profile: epson-tm-t20iii, connections: [ { tcp: { port: 9100 }, serial: { pty: true } } ] } ]\n"

    assert "exactly one of `tcp` or `serial`" in issues_of(text)["devices[0].connections[0]"]


def test_duplicate_tcp_port_names_both_paths() -> None:
    text = f"schema: 1\ndevices:\n  - {PRINTER}\n  - {{ id: kitchen, type: printer, profile: epson-tm-t20iii, connections: [ {{ tcp: {{ port: 9100 }} }} ] }}\n"

    message = issues_of(text)["devices[1].connections[0].tcp.port"]

    assert "9100" in message
    assert "devices[0].connections[0].tcp.port" in message


def test_tcp_port_equal_to_api_port() -> None:
    text = "schema: 1\napi: { port: 8765 }\ndevices: [ { id: front, type: printer, profile: epson-tm-t20iii, connections: [ { tcp: { port: 8765 } } ] } ]\n"

    assert "8765" in issues_of(text)["devices[0].connections[0].tcp.port"]


def test_pty_is_rejected_on_windows() -> None:
    text = "schema: 1\ndevices: [ { id: deli, type: scale, profile: toledo8217-15kg, connections: [ { serial: { pty: true } } ] } ]\n"

    message = issues_of(text, platform="win32")["devices[0].connections[0].serial"]

    assert "com0com" in message
    assert "port" in message


def test_link_defaults_to_device_id_and_duplicates_are_rejected() -> None:
    text = """
schema: 1
devices:
  - { id: deli, type: scale, profile: toledo8217-15kg, connections: [ { serial: { pty: true } } ] }
  - { id: lane2, type: scanner, mode: serial, connections: [ { serial: { pty: true, link: deli } } ] }
"""
    assert "link `deli`" in issues_of(text)["devices[1].connections[0].serial.link"]


# --- defaults, paths, profiles -------------------------------------------------------------


def test_minimal_configuration_defaults() -> None:
    loaded = parse(f"schema: 1\ndevices: [ {PRINTER} ]\n")
    printer = loaded.config.devices[0]

    assert isinstance(printer, PrinterDevice)
    assert (loaded.config.api.host, loaded.config.api.port) == ("127.0.0.1", 8765)
    assert printer.connections[0].tcp is not None
    assert printer.connections[0].tcp.host == "127.0.0.1"
    assert printer.job_idle_timeout_ms == 2000


def test_receipts_dir_is_relative_to_the_config_file(tmp_path: Path) -> None:
    file = tmp_path / "pos" / "emupos.yaml"
    file.parent.mkdir()
    file.write_text(f"schema: 1\ndevices: [ {PRINTER} ]\n")

    loaded = load_config_file(file)
    printer = loaded.config.devices[0]

    assert isinstance(printer, PrinterDevice)
    assert loaded.receipts_dir(printer) == (tmp_path / "pos" / "receipts").resolve()


def test_drawer_sensor_level_defaults_to_profile() -> None:
    loaded = parse(f"schema: 1\ndevices: [ {PRINTER} ]\n")
    printer = loaded.config.devices[0]

    assert isinstance(printer, PrinterDevice)
    assert loaded.drawer_sensor_open_level(printer) == "high"


def test_unknown_profile_lists_builtins_of_the_type() -> None:
    text = "schema: 1\ndevices: [ { id: front, type: printer, profile: epson-tm-t88, connections: [ { tcp: { port: 9100 } } ] } ]\n"

    message = issues_of(text)["devices[0].profile"]

    assert "epson-tm-t20iii, rongta-rp326, xprinter-xp80t" in message


def test_user_provided_profile(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    builtin = parse(f"schema: 1\ndevices: [ {PRINTER} ]\n").printer_profile("front")
    custom = builtin.model_dump() | {"name": "My 80mm", "width_dots": 512}
    (profiles / "my-80mm.yaml").write_text(yaml.safe_dump(custom))

    text = "schema: 1\ndevices: [ { id: front, type: printer, profile: ./profiles/my-80mm.yaml, connections: [ { tcp: { port: 9100 } } ] } ]\n"
    loaded = parse(text, base_dir=tmp_path)

    assert loaded.printer_profile("front").width_dots == 512


def test_invalid_user_provided_profile_names_file_and_key(tmp_path: Path) -> None:
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "my-80mm.yaml").write_text("type: printer\nname: broken\n")
    text = "schema: 1\ndevices: [ { id: front, type: printer, profile: ./profiles/my-80mm.yaml, connections: [ { tcp: { port: 9100 } } ] } ]\n"

    with pytest.raises(ConfigError) as error:
        parse(text, base_dir=tmp_path)

    message = str(error.value)
    assert "./profiles/my-80mm.yaml" in message
    assert "width_dots" in message


def test_every_builtin_profile_loads() -> None:
    text = """
schema: 1
devices:
  - { id: a, type: printer, profile: epson-tm-t20iii, connections: [ { tcp: { port: 9101 } } ] }
  - { id: b, type: printer, profile: xprinter-xp80t, connections: [ { tcp: { port: 9102 } } ] }
  - { id: c, type: printer, profile: rongta-rp326, connections: [ { tcp: { port: 9103 } } ] }
  - { id: d, type: scale, profile: toledo8217-15kg, connections: [ { serial: { pty: true } } ] }
"""
    loaded = parse(text)

    assert loaded.printer_profile("a").code_pages[37] == "PC864"
    assert loaded.printer_profile("c").code_pages[22] == "PC864"
    scale = loaded.scale_profile("d")
    assert scale.capacity_grams == 15000
    assert (
        scale.serial.baud,
        scale.serial.data_bits,
        scale.serial.parity,
        scale.serial.stop_bits,
    ) == (
        9600,
        7,
        "even",
        1,
    )


# --- starter, schema, demo -----------------------------------------------------------------


def test_starter_configuration_is_valid() -> None:
    loaded = parse(starter_config_text())

    assert [device.id for device in loaded.config.devices] == ["front"]


def test_starter_validates_against_json_schema() -> None:
    jsonschema.validate(yaml.safe_load(starter_config_text()), json_schema())


def test_json_schema_rejects_unknown_keys() -> None:
    document: dict[str, object] = {
        "schema": 1,
        "devices": [{"id": "front", "type": "printer", "profile": "x", "conections": []}],
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, json_schema())


def test_demo_on_windows_has_no_serial_scale(tmp_path: Path) -> None:
    loaded = demo_config(platform="win32", cwd=tmp_path)

    assert sorted(device.type for device in loaded.config.devices) == ["printer", "scanner"]


def test_demo_on_macos_includes_pty_scale(tmp_path: Path) -> None:
    loaded = demo_config(platform="darwin", cwd=tmp_path)

    assert sorted(device.type for device in loaded.config.devices) == [
        "printer",
        "scale",
        "scanner",
    ]
