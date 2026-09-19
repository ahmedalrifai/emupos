"""Commands without a running simulator: help, usage errors, exit status 3, the API address."""

import json
import re
import sys
from importlib.metadata import version

import pytest
from typer.testing import CliRunner

from emupos.cli.app import app
from emupos.transports.ports import tcp_port_free

runner = CliRunner()
FAULT_NAMES = ("paper-near-end", "paper-out", "cover-open", "offline")


def words(text: str) -> str:
    """Help and usage errors are drawn in wrapped panels, styled when Typer forces a terminal
    (it does under GITHUB_ACTIONS): compare their words only."""
    plain = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return " ".join(plain.replace("│", " ").split())


def unused_api() -> str:
    port = next(port for port in range(47000, 48000) if tcp_port_free("127.0.0.1", port))
    return f"http://127.0.0.1:{port}"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EMUPOS_API", "NO_COLOR", "FORCE_COLOR"):
        monkeypatch.delenv(name, raising=False)


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout == f"emupos {version('emupos')}\n"


@pytest.mark.parametrize(
    "command",
    [
        [],
        ["run"],
        ["devices"],
        ["receipt"],
        ["receipt", "list"],
        ["receipt", "show"],
        ["scan"],
        ["scale"],
        ["scale", "set"],
        ["scale", "zero"],
        ["scale", "tare"],
        ["fault"],
        ["fault", "set"],
        ["fault", "clear"],
        ["drawer"],
        ["drawer", "close"],
        ["barcode"],
        ["barcode", "weighed"],
        ["config"],
        ["config", "init"],
        ["config", "validate"],
        ["config", "schema"],
        ["doctor"],
        ["setup"],
        ["setup", "print-queue"],
    ],
)
def test_every_command_has_help(command: list[str]) -> None:
    result = runner.invoke(app, [*command, "--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.stdout


def test_scale_set_help_describes_its_arguments() -> None:
    result = runner.invoke(app, ["scale", "set", "--help"])
    assert result.exit_code == 0
    for text in ("VALUE", "--device", "--unstable"):
        assert text in words(result.stdout)


def test_simulator_not_running_exits_3_naming_the_url() -> None:
    api = unused_api()
    result = runner.invoke(app, ["--api", api, "devices"])
    assert result.exit_code == 3
    assert api in result.stderr
    assert "emupos run" in result.stderr
    assert result.stdout == ""


def test_default_api_url_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    if not tcp_port_free("127.0.0.1", 8765):
        pytest.skip("something listens on 127.0.0.1:8765")
    result = runner.invoke(app, ["devices"])
    assert result.exit_code == 3
    assert "http://127.0.0.1:8765" in result.stderr


def test_json_error_is_the_error_body_on_stderr() -> None:
    result = runner.invoke(app, ["--api", unused_api(), "devices", "--json"])
    assert result.exit_code == 3
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "simulator_unreachable"
    assert set(error) == {"code", "message", "fix"}


def test_option_overrides_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from_env, from_option = unused_api(), "http://127.0.0.1:1"
    monkeypatch.setenv("EMUPOS_API", from_env)
    result = runner.invoke(app, ["--api", from_option, "devices"])
    assert from_option in result.stderr
    assert from_env not in result.stderr


def test_environment_variable_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    api = unused_api()
    monkeypatch.setenv("EMUPOS_API", api)
    result = runner.invoke(app, ["devices"])
    assert result.exit_code == 3
    assert api in result.stderr


@pytest.mark.parametrize("value", ["ftp://127.0.0.1:8765", "127.0.0.1:8765", "http://"])
def test_api_that_is_not_http_is_a_usage_error(value: str) -> None:
    result = runner.invoke(app, ["--api", value, "devices"])
    assert result.exit_code == 2


def test_weight_without_unit_is_a_usage_error_before_any_request() -> None:
    result = runner.invoke(app, ["--api", unused_api(), "scale", "set", "heavy"])
    assert result.exit_code == 2  # not 3: the simulator was never contacted
    assert "e.g. 1.25kg or 1250g" in words(result.stderr)


def test_sub_gram_weight_is_a_usage_error() -> None:
    result = runner.invoke(app, ["--api", unused_api(), "scale", "set", "1.2505kg"])
    assert result.exit_code == 2
    assert "weights are whole grams" in words(result.stderr)


@pytest.mark.parametrize("args", [["-100g"], ["--", "-100g"], ["-100g", "--unstable"]])
def test_negative_weights_parse(args: list[str]) -> None:
    result = runner.invoke(app, ["--api", unused_api(), "scale", "set", *args])
    assert result.exit_code == 3  # the value was accepted; only the simulator is missing


def test_unknown_fault_is_a_usage_error_listing_the_faults() -> None:
    result = runner.invoke(app, ["--api", unused_api(), "fault", "set", "front", "jammed"])
    assert result.exit_code == 2
    for name in FAULT_NAMES:
        assert name in words(result.stderr)


def test_fault_names_complete_in_the_shell() -> None:
    env = {"_EMUPOS_COMPLETE": "complete_zsh", "_TYPER_COMPLETE_ARGS": "emupos fault set front pa"}
    result = runner.invoke(app, [], env=env, prog_name="emupos")
    assert "paper-near-end" in result.stdout
    assert "paper-out" in result.stdout
    assert "cover-open" not in result.stdout


def test_negative_countdown_is_a_usage_error() -> None:
    result = runner.invoke(app, ["--api", unused_api(), "scan", "123", "--countdown", "-1"])
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "command",
    [
        ["receipt", "list"],
        ["scan", "123"],
        ["scale", "zero"],
        ["drawer", "close"],
    ],
)
def test_a_device_that_is_not_an_id_is_a_usage_error(command: list[str]) -> None:
    result = runner.invoke(app, ["--api", unused_api(), *command, "--device", "Front Desk"])
    assert result.exit_code == 2  # not 3: the simulator was never contacted
    assert "is not a device id" in words(result.stderr)


def test_unknown_command_is_a_usage_error() -> None:
    assert runner.invoke(app, ["printers"]).exit_code == 2


@pytest.mark.skipif(sys.platform == "win32", reason="print queues exist on Windows")
def test_print_queue_is_refused_outside_windows() -> None:
    result = runner.invoke(
        app, ["--api", unused_api(), "setup", "print-queue", "--device", "front"]
    )
    assert result.exit_code == 1
    assert "only supported on Windows" in result.stderr
    assert "TCP port or serial connection directly" in result.stderr
