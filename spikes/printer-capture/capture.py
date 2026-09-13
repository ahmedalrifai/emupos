# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Capture raw ESC/POS jobs sent to a fake network printer.

Listens on 127.0.0.1:9100 (like a real printer's raw port) and saves the bytes of every
connection as spaced hex, one file per connection, in the output directory:

    uv run spikes/printer-capture/capture.py captures/          # writes 001.hex, 002.hex, ...

Point a POS or an ESC/POS library at 127.0.0.1:9100 and print. Stop with Ctrl+C.
It never replies, so drivers that wait for status bytes will time out on those queries.
"""

import argparse
import contextlib
import socketserver
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="directory for the .hex files")
    parser.add_argument("--port", type=int, default=9100)
    args = parser.parse_args()
    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)
    counter = len(list(output.glob("*.hex")))

    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            nonlocal counter
            data = bytearray()
            while chunk := self.request.recv(65536):
                data += chunk
            counter += 1
            path = output / f"{counter:03d}.hex"
            path.write_text(to_spaced_hex(bytes(data)))
            print(f"{path}: {len(data)} bytes")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"listening on 127.0.0.1:{args.port}, saving to {output}/")
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever()


def to_spaced_hex(data: bytes, per_line: int = 32) -> str:
    lines = [data[i : i + per_line].hex(" ") for i in range(0, len(data), per_line)]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
