"""Release smoke test: run against the installed wheel, never the source tree.

    python .github/scripts/smoke_test.py X.Y.Z

Checks that `emupos --version` reports the release version, that `emupos doctor --json`
prints a JSON report, and that a simulated printer turns a fixture ESC/POS job into the
expected receipt text. Uses only the standard library so it runs in a bare venv.
"""

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RECEIPT_JOB = bytes.fromhex("1b 40 48 69 0a 1d 56 00")  # ESC @, "Hi", LF, GS V 0 (cut)
TIMEOUT = 20.0


def emupos(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "emupos.cli.app", *args]
    return subprocess.run(
        command, capture_output=True, text=True, cwd=cwd, timeout=TIMEOUT, check=False
    )


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until(check: object, what: str) -> None:
    assert callable(check)
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise SystemExit(f"timed out waiting for {what}")


def check_version(expected: str) -> None:
    result = emupos("--version")
    if result.stdout.strip() != f"emupos {expected}":
        raise SystemExit(
            f"`emupos --version` printed {result.stdout!r}, expected 'emupos {expected}'"
        )


def check_doctor() -> None:
    report = json.loads(emupos("doctor", "--json").stdout)
    if "checks" not in report:
        raise SystemExit(f"`emupos doctor --json` printed no checks: {report}")


def check_receipt() -> None:
    api_port, printer_port = free_port(), free_port()
    with tempfile.TemporaryDirectory() as directory:
        workdir = Path(directory)
        (workdir / "emupos.yaml").write_text(
            f"schema: 1\napi: {{ port: {api_port} }}\ndevices:\n"
            f"  - {{ id: front, type: printer, profile: epson-tm-t20iii, connections: [ {{ tcp: {{ port: {printer_port} }} }} ] }}\n",
            encoding="utf-8",
        )
        command = [sys.executable, "-m", "emupos.cli.app", "run"]
        process = subprocess.Popen(
            command, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        api = f"http://127.0.0.1:{api_port}/api/v1"
        try:
            wait_until(
                lambda: urllib.request.urlopen(f"{api}/health", timeout=2).status == 200,
                "the control API",
            )
            with socket.create_connection(("127.0.0.1", printer_port), timeout=5) as printer:
                printer.sendall(RECEIPT_JOB)
            text_url = f"{api}/devices/front/receipts/latest/text"
            wait_until(
                lambda: urllib.request.urlopen(text_url, timeout=2).read().decode().strip() == "Hi",
                "the receipt",
            )
        finally:
            process.terminate()
            output, _ = process.communicate(timeout=TIMEOUT)
        # Raw bytes: a Windows console's code page (cp1252) cannot show every character emupos prints.
        sys.stdout.buffer.write(output)
        sys.stdout.flush()


def main() -> None:
    expected = sys.argv[1]
    check_version(expected)
    check_doctor()
    check_receipt()
    print(f"smoke test passed for emupos {expected}")


if __name__ == "__main__":
    main()
