"""Release smoke test for the container image, run from outside the container.

    python .github/scripts/image_smoke_test.py emupos:candidate

Starts the image with its ports published to 127.0.0.1 and checks, from the host, that the
control API answers and that a fixture ESC/POS job sent to the published printer port becomes
the expected receipt text. Running the checks inside the container would pass even when the
image binds loopback only, which is the mistake this test exists to catch (design D7).

Uses only the standard library, and leaves no container behind.
"""

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

RECEIPT_JOB = bytes.fromhex("1b 40 48 69 0a 1d 56 00")  # ESC @, "Hi", LF, GS V 0 (cut)
NAME = "emupos-image-smoke"
TIMEOUT = 30.0


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
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise SystemExit(f"timed out waiting for {what}")


def docker(*args: str) -> str:
    if (executable := shutil.which("docker")) is None:
        raise SystemExit("docker is not on PATH")
    result = subprocess.run(
        [executable, *args], capture_output=True, text=True, timeout=TIMEOUT * 2, check=False
    )
    if result.returncode != 0:
        raise SystemExit(f"`docker {' '.join(args)}` failed:\n{result.stdout}{result.stderr}")
    return result.stdout


def check_image(image: str) -> None:
    api_port, printer_port = free_port(), free_port()
    docker("rm", "-f", NAME)
    docker(
        "run", "-d", "--name", NAME,
        "-p", f"127.0.0.1:{api_port}:8765",
        "-p", f"127.0.0.1:{printer_port}:9100",
        image,
    )  # fmt: skip
    api = f"http://127.0.0.1:{api_port}/api/v1"
    try:
        wait_until(
            lambda: json.load(urllib.request.urlopen(f"{api}/health", timeout=2))["status"] == "ok",
            "the control API, published to the host",
        )
        with socket.create_connection(("127.0.0.1", printer_port), timeout=5) as printer:
            printer.sendall(RECEIPT_JOB)
        text_url = f"{api}/devices/front/receipts/latest/text"
        wait_until(
            lambda: urllib.request.urlopen(text_url, timeout=2).read().decode().strip() == "Hi",
            "the receipt",
        )
        if "root" in docker("exec", NAME, "id", "-un"):
            raise SystemExit("the image runs as root")
    finally:
        sys.stdout.write(docker("logs", NAME))
        docker("rm", "-f", NAME)


def main() -> None:
    image = sys.argv[1]
    check_image(image)
    print(f"image smoke test passed for {image}")


if __name__ == "__main__":
    main()
