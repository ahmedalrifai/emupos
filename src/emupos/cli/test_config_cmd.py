import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from emupos.cli.app import app
from emupos.config import starter_config_text

runner = CliRunner()

VALID = """\
schema: 1
devices:
  - id: front
    type: printer
    profile: epson-tm-t20iii
    connections: [{ tcp: { port: 9100 } }]
  - id: deli
    type: scale
    profile: toledo8217-15kg
    connections: [{ tcp: { port: 9200 } }]
  - id: lane1
    type: scanner
    mode: keyboard
"""

TWO_ERRORS = """\
schema: 1
devices:
  - id: cash
    type: drawer
  - id: front
    type: printer
    profile: epson-tm-t20iii
    connections: [{ tcp: { port: 0 } }]
"""


@pytest.fixture(autouse=True)
def in_empty_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for name in ("EMUPOS_API", "NO_COLOR", "FORCE_COLOR"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_init_writes_the_starter(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert (tmp_path / "emupos.yaml").read_text(encoding="utf-8") == starter_config_text()


def test_init_to_a_path(tmp_path: Path) -> None:
    assert runner.invoke(app, ["config", "init", "lane2.yaml"]).exit_code == 0
    assert (tmp_path / "lane2.yaml").is_file()


def test_init_keeps_an_existing_file(tmp_path: Path) -> None:
    (tmp_path / "emupos.yaml").write_text("mine", encoding="utf-8")
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 1
    assert "emupos.yaml" in result.stderr
    assert (tmp_path / "emupos.yaml").read_text(encoding="utf-8") == "mine"


def test_starter_is_valid() -> None:
    runner.invoke(app, ["config", "init"])
    assert runner.invoke(app, ["config", "validate"]).exit_code == 0


def test_validate_lists_devices(tmp_path: Path) -> None:
    (tmp_path / "emupos.yaml").write_text(VALID, encoding="utf-8")
    result = runner.invoke(app, ["--api", "http://127.0.0.1:1", "config", "validate"])
    assert result.exit_code == 0
    for device, kind in (("front", "printer"), ("deli", "scale"), ("lane1", "scanner")):
        line = next(line for line in result.stdout.splitlines() if line.startswith(device))
        assert kind in line


def test_validate_without_a_file_names_the_path(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "validate"])
    assert result.exit_code == 2
    assert str(tmp_path / "emupos.yaml") in result.stderr
    assert "emupos config init" in result.stderr


def test_validate_reports_every_error(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(TWO_ERRORS, encoding="utf-8")
    result = runner.invoke(app, ["config", "validate", "bad.yaml"])
    assert result.exit_code == 1
    assert "devices[0].type" in result.stderr
    assert "devices[1].connections[0].tcp.port" in result.stderr


def test_validate_newer_schema(tmp_path: Path) -> None:
    (tmp_path / "emupos.yaml").write_text("schema: 2\n", encoding="utf-8")
    result = runner.invoke(app, ["config", "validate"])
    assert result.exit_code == 1
    assert "schema 2" in result.stderr
    assert "upgrade emupos" in result.stderr


def test_schema_is_json_schema() -> None:
    result = runner.invoke(app, ["config", "schema"])
    assert result.exit_code == 0
    assert "json-schema.org" in json.loads(result.stdout)["$schema"]


def test_run_without_a_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 2
    assert str(tmp_path / "emupos.yaml") in result.stderr
    assert "emupos config init" in result.stderr


def test_run_demo_and_config_are_mutually_exclusive(tmp_path: Path) -> None:
    (tmp_path / "emupos.yaml").write_text(VALID, encoding="utf-8")
    result = runner.invoke(app, ["run", "--demo", "--config", "emupos.yaml"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.stderr


def test_run_with_an_invalid_file_opens_nothing(tmp_path: Path) -> None:
    (tmp_path / "emupos.yaml").write_text(TWO_ERRORS, encoding="utf-8")
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 1
    assert "devices[0].type" in result.stderr
    assert "devices[1].connections[0].tcp.port" in result.stderr
