from pathlib import Path

import pytest
import zxingcpp
from PIL import Image
from typer.testing import CliRunner

from emupos.cli.app import app

runner = CliRunner()
SIMULATOR_NOT_RUNNING = ["--api", "http://127.0.0.1:1"]


@pytest.fixture(autouse=True)
def in_empty_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def weighed(*args: str) -> list[str]:
    return [*SIMULATOR_NOT_RUNNING, "barcode", "weighed", *args]


def test_weight_barcode_prints_exactly_the_digits() -> None:
    result = runner.invoke(
        app, weighed("--layout", "weight-21", "--item", "12345", "--weight", "1.25kg")
    )
    assert result.exit_code == 0
    assert result.stdout == "2112345012506\n"


def test_price_barcode_without_the_simulator() -> None:
    result = runner.invoke(
        app, weighed("--layout", "23IIIIIPPPPPC", "--item", "12345", "--price", "1299")
    )
    assert result.exit_code == 0
    assert result.stdout == "2312345012999\n"


def test_weight_and_price_are_mutually_exclusive(tmp_path: Path) -> None:
    args = ("--layout", "weight-21", "--item", "12345", "--weight", "1250g", "--price", "1299")
    result = runner.invoke(app, weighed(*args, "--save", "label.png"))
    assert result.exit_code == 2
    assert "--weight and --price are mutually exclusive" in result.stderr
    assert not (tmp_path / "label.png").exists()


def test_rejected_input_prints_message_and_fix(tmp_path: Path) -> None:
    args = ("--layout", "21IIIIIWWWWWC", "--item", "12345", "--weight", "123456g")
    result = runner.invoke(app, weighed(*args, "--save", "label.png"))
    assert result.exit_code == 2
    assert "99999 g" in result.stderr
    assert "fix:" in result.stderr
    assert not (tmp_path / "label.png").exists()


def test_invalid_weight_is_a_usage_error() -> None:
    result = runner.invoke(app, weighed("--layout", "weight-21", "--item", "1", "--weight", "1.25"))
    assert result.exit_code == 2
    assert "1250g" in result.stderr


def test_save_writes_a_decodable_label(tmp_path: Path) -> None:
    args = ("--layout", "weight-21", "--item", "12345", "--weight", "1.25kg", "--save", "label.png")
    result = runner.invoke(app, weighed(*args))
    assert result.exit_code == 0
    assert result.stdout == "2112345012506\n"
    with Image.open(tmp_path / "label.png") as image:
        texts = [found.text for found in zxingcpp.read_barcodes(image)]
    assert texts == ["2112345012506"]


def test_unwritable_save_path_names_it() -> None:
    args = ("--layout", "weight-21", "--item", "12345", "--weight", "1.25kg")
    result = runner.invoke(app, weighed(*args, "--save", "missing/label.png"))
    assert result.exit_code == 1
    assert str(Path("missing/label.png")) in result.stderr
