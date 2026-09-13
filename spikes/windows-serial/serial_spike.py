# /// script
# requires-python = ">=3.13"
# dependencies = ["serialx==1.10.0", "pyserial==3.5"]
# ///
"""Windows serial spike (task 1.1): is serialx reliable against a com0com pair, or should
emupos default to pyserial in a worker thread?

Give it both ends of a virtual pair. The "sim" end plays emupos, the "client" end plays
the POS:

    uv run spikes/windows-serial/serial_spike.py COM5 COM6
    uv run spikes/windows-serial/serial_spike.py COM5 COM6 --backend pyserial --cycles 20

For each backend it runs N cycles of:

    open sim -> open client -> all 256 byte values client->sim and sim->client
    -> close client -> sim writes while the client is closed (blocks? errors? succeeds?)
    -> reopen client -> any stale bytes from that write arrive? -> round trip again
    -> close both

then checks framing: the client at 9600 7E1 against a sim at 8N1 and at 7E1.

Backends:
- serialx: its own asyncio transport (`serialx.async_serial_for_url(...)` -> `AsyncSerial`
  with `open/write/flush/readexactly/read/close`). On Windows it needs the Proactor event
  loop, which is the default. `write()` only drains the asyncio buffer; `flush()` waits for
  the OS queue (FlushFileBuffers in an executor thread), so the peer-closed test uses both.
- pyserial: the blocking `serial.Serial` API, each call run with `asyncio.to_thread`.

Every step has a timeout. A worker thread stuck inside the OS cannot be cancelled, so the
script exits with os._exit() after writing results rather than waiting for it.
Results: printed as JSON and written to result-<backend>[-<label>].json next to this file.
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import threading
import time
import traceback
from collections import Counter
from pathlib import Path

import serial  # pyserial
import serialx

HERE = Path(__file__).parent
OPEN_TIMEOUT = 5.0  # seconds
IO_TIMEOUT = 2.0  # one read or write inside a backend (256 bytes at 9600 baud take ~0.3 s)
STEP_TIMEOUT = 2 * IO_TIMEOUT + 1  # outer asyncio safety net: a write plus its flush wait
STALE_WAIT = 0.5  # how long to listen for stale bytes after reopening
ALL_BYTES = bytes(range(256))
STALE_PAYLOAD = b"written-while-client-closed"
MAX_FAILURES_KEPT = 20

Framing = tuple[int, int, str, int]  # baud, data bits, parity, stop bits
FRAMING_8N1: Framing = (9600, 8, "N", 1)
FRAMING_7E1: Framing = (9600, 7, "E", 1)


class SerialxPort:
    """serialx asyncio API."""

    def __init__(self, name: str, framing: Framing) -> None:
        self.name, self.framing = name, framing
        self._port: serialx.AsyncSerial | None = None

    async def open(self) -> None:
        baud, bits, parity, stop = self.framing
        self._port = serialx.async_serial_for_url(
            self.name,
            baudrate=baud,
            byte_size=bits,
            parity=serialx.Parity(parity),
            stopbits=serialx.StopBits(stop),
        )
        await self._port.open()

    async def write(self, data: bytes) -> None:
        assert self._port is not None
        await self._port.write(data)
        await self._port.flush()

    async def read(self, size: int) -> bytes:
        assert self._port is not None
        return await self._port.readexactly(size)

    async def read_pending(self, wait: float) -> bytes:
        assert self._port is not None
        received = bytearray()
        try:
            while True:
                async with asyncio.timeout(wait):
                    chunk = await self._port.read(4096)
                if not chunk:
                    break
                received += chunk
        except TimeoutError:
            pass
        return bytes(received)

    async def close(self) -> None:
        if self._port is not None:
            port, self._port = self._port, None
            await port.close()


class PyserialPort:
    """pyserial blocking API, one worker thread per call via asyncio.to_thread."""

    def __init__(self, name: str, framing: Framing) -> None:
        self.name, self.framing = name, framing
        self._port: serial.Serial | None = None

    async def open(self) -> None:
        baud, bits, parity, stop = self.framing
        self._port = await asyncio.to_thread(
            serial.Serial,
            self.name,
            baudrate=baud,
            bytesize=bits,
            parity=parity,
            stopbits=stop,
            timeout=IO_TIMEOUT,
            write_timeout=IO_TIMEOUT,
        )

    async def write(self, data: bytes) -> None:
        await asyncio.to_thread(self._write_blocking, data)

    def _write_blocking(self, data: bytes) -> None:
        assert self._port is not None
        written = self._port.write(data)  # raises SerialTimeoutException after write_timeout
        if written != len(data):
            raise OSError(f"wrote {written} of {len(data)} bytes")
        # ponytail: pyserial's flush() polls out_waiting with no timeout; poll with a deadline.
        deadline = time.monotonic() + IO_TIMEOUT
        while self._port.out_waiting:
            if time.monotonic() > deadline:
                raise TimeoutError(f"{self._port.out_waiting} bytes still in the output queue")
            time.sleep(0.01)

    async def read(self, size: int) -> bytes:
        assert self._port is not None
        data = await asyncio.to_thread(self._port.read, size)
        if len(data) < size:
            raise TimeoutError(f"received {len(data)} of {size} bytes")
        return data

    async def read_pending(self, wait: float) -> bytes:
        return await asyncio.to_thread(self._read_pending_blocking, wait)

    def _read_pending_blocking(self, wait: float) -> bytes:
        assert self._port is not None
        self._port.timeout = wait
        try:
            return self._port.read(65536)
        finally:
            self._port.timeout = IO_TIMEOUT

    async def close(self) -> None:
        if self._port is not None:
            port, self._port = self._port, None
            await asyncio.to_thread(port.close)


BACKENDS = {"serialx": SerialxPort, "pyserial": PyserialPort}
Port = SerialxPort | PyserialPort


class DataMismatchError(Exception):
    pass


async def step(trace: list[str], label: str, awaitable, timeout: float = STEP_TIMEOUT):
    """Run one step under a timeout; `trace[-1]` names the step that failed."""
    trace.append(label)
    async with asyncio.timeout(timeout):
        return await awaitable


async def round_trip(
    sim: Port, client: Port, latency: dict[str, list[float]], trace: list[str]
) -> None:
    for direction, sender, receiver in (("client->sim", client, sim), ("sim->client", sim, client)):
        started = time.perf_counter()
        received, _ = await step(
            trace,
            f"round trip {direction}",
            asyncio.gather(receiver.read(len(ALL_BYTES)), sender.write(ALL_BYTES)),
        )
        if received != ALL_BYTES:
            first_diff = next(
                i for i, (a, b) in enumerate(zip(received, ALL_BYTES, strict=True)) if a != b
            )
            raise DataMismatchError(f"{direction}: first difference at byte {first_diff}")
        latency[direction].append((time.perf_counter() - started) * 1000)


async def write_while_peer_closed(sim: Port) -> tuple[str, float]:
    """Outcome of a write with nobody on the other end: accepted, blocked or an error."""
    started = time.perf_counter()
    try:
        async with asyncio.timeout(STEP_TIMEOUT):
            await sim.write(STALE_PAYLOAD)
        outcome = "accepted"
    except (TimeoutError, serial.SerialTimeoutException) as exc:
        # The reason tells apart a blocked write call from data stuck in the OS queue.
        outcome = f"blocked: {type(exc).__name__}: {exc}"
    except Exception as exc:  # the point is to record whatever happens
        outcome = f"error: {type(exc).__name__}: {exc}"
    return outcome, (time.perf_counter() - started) * 1000


async def close_quietly(port: Port) -> None:
    try:
        async with asyncio.timeout(STEP_TIMEOUT):
            await port.close()
    except Exception as exc:  # cleanup after a failure; the failure itself is already recorded
        print(f"  (close {port.name} failed: {exc!r})")


async def run_cycle(
    backend: type[Port], args: argparse.Namespace, stats: dict, trace: list[str]
) -> None:
    sim = backend(args.sim_port, FRAMING_8N1)
    client = backend(args.client_port, FRAMING_8N1)
    try:
        started = time.perf_counter()
        await step(trace, "open sim", sim.open(), OPEN_TIMEOUT)
        await step(trace, "open client", client.open(), OPEN_TIMEOUT)
        stats["open_ms"].append((time.perf_counter() - started) * 1000)
        await round_trip(sim, client, stats["latency_ms"], trace)

        await step(trace, "close client", client.close())
        trace.append("write while client closed")
        outcome, elapsed_ms = await write_while_peer_closed(sim)
        stats["write_while_peer_closed"][outcome] += 1
        stats["write_while_peer_closed_ms"].append(elapsed_ms)

        await step(trace, "reopen client", client.open(), OPEN_TIMEOUT)
        stale = await step(trace, "read stale bytes", client.read_pending(STALE_WAIT))
        stats["stale_after_reopen"][classify_stale(stale)] += 1
        await round_trip(sim, client, stats["latency_ms"], trace)
    finally:
        await close_quietly(client)
        await close_quietly(sim)


def classify_stale(data: bytes) -> str:
    if not data:
        return "none"
    if data == STALE_PAYLOAD:
        return "all stale bytes delivered"
    return f"{len(data)} bytes: {data[:32]!r}"


async def check_framing(
    backend: type[Port], args: argparse.Namespace, sim_framing: Framing
) -> dict:
    """Client at 9600 7E1; does every byte value still arrive unchanged?"""
    sim = backend(args.sim_port, sim_framing)
    client = backend(args.client_port, FRAMING_7E1)
    result: dict = {"sim": framing_name(sim_framing), "client": framing_name(FRAMING_7E1)}
    trace: list[str] = []
    try:
        await step(trace, "open sim", sim.open(), OPEN_TIMEOUT)
        await step(trace, "open client", client.open(), OPEN_TIMEOUT)
        for direction, sender, receiver in (
            ("client->sim", client, sim),
            ("sim->client", sim, client),
        ):
            try:
                received, _ = await step(
                    trace,
                    direction,
                    asyncio.gather(receiver.read(len(ALL_BYTES)), sender.write(ALL_BYTES)),
                )
                result[direction] = compare_bytes(received)
            except Exception as exc:
                result[direction] = f"error at '{trace[-1]}': {exc!r}"
    except Exception as exc:
        result["error"] = f"at '{trace[-1]}': {exc!r}"
    finally:
        await close_quietly(client)
        await close_quietly(sim)
    return result


def compare_bytes(received: bytes) -> str:
    if received == ALL_BYTES:
        return "exact"
    if received == bytes(b & 0x7F for b in ALL_BYTES):
        return "top bit stripped (7-bit)"
    return f"different: {received[:16].hex(' ')}..."


def framing_name(framing: Framing) -> str:
    baud, bits, parity, stop = framing
    return f"{baud} {bits}{parity}{stop}"


def summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    p95 = (
        statistics.quantiles(values, n=20, method="inclusive")[-1] if len(values) > 1 else values[0]
    )
    return {
        "n": len(values),
        "min": round(min(values), 2),
        "median": round(statistics.median(values), 2),
        "p95": round(p95, 2),
        "max": round(max(values), 2),
    }


async def run_backend(name: str, args: argparse.Namespace) -> dict:
    backend = BACKENDS[name]
    stats: dict = {
        "open_ms": [],
        "latency_ms": {"client->sim": [], "sim->client": []},
        "write_while_peer_closed": Counter(),
        "write_while_peer_closed_ms": [],
        "stale_after_reopen": Counter(),
    }
    failures, failure_steps, started = [], Counter(), time.monotonic()
    for cycle in range(1, args.cycles + 1):
        trace: list[str] = []
        try:
            await run_cycle(backend, args, stats, trace)
        except Exception as exc:
            step_name = trace[-1] if trace else "start"
            failure_steps[step_name] += 1
            if len(failures) < MAX_FAILURES_KEPT:
                failures.append({"cycle": cycle, "step": step_name, "error": repr(exc)})
            print(f"  cycle {cycle}: FAILED at {step_name}: {exc!r}")
        if cycle % 10 == 0:
            print(f"  {name}: {cycle}/{args.cycles} cycles, {sum(failure_steps.values())} failed")

    framing = [await check_framing(backend, args, f) for f in (FRAMING_8N1, FRAMING_7E1)]
    return {
        "backend": name,
        "label": args.label,
        "sim_port": args.sim_port,
        "client_port": args.client_port,
        "platform": platform.platform(),
        "python": sys.version,
        "serialx": importlib.metadata.version("serialx"),
        "pyserial": importlib.metadata.version("pyserial"),
        "cycles": args.cycles,
        "cycles_failed": sum(failure_steps.values()),
        "failures_by_step": dict(failure_steps),
        "failures": failures,
        "open_ms": summary(stats["open_ms"]),
        "latency_ms": {k: summary(v) for k, v in stats["latency_ms"].items()},
        "write_while_peer_closed": dict(stats["write_while_peer_closed"]),
        "write_while_peer_closed_ms": summary(stats["write_while_peer_closed_ms"]),
        "stale_after_reopen": dict(stats["stale_after_reopen"]),
        "framing_client_7e1": framing,
        "elapsed_s": round(time.monotonic() - started, 1),
        "threads_alive_at_end": threading.active_count() - 1,
    }


async def run_all(args: argparse.Namespace) -> int:
    names = list(BACKENDS) if args.backend == "both" else [args.backend]
    exit_code = 0
    for name in names:
        print(f"== {name}: {args.cycles} cycles on sim={args.sim_port} client={args.client_port}")
        result = await run_backend(name, args)
        suffix = f"-{args.label}" if args.label else ""
        path = HERE / f"result-{name}{suffix}.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        print(f"== wrote {path}")
        if result["cycles_failed"]:
            exit_code = 1
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sim_port", help="port emupos would open, e.g. COM5")
    parser.add_argument("client_port", help="port the POS would open, e.g. COM6")
    parser.add_argument("--backend", choices=["both", *BACKENDS], default="both")
    parser.add_argument("--cycles", type=int, default=100)
    parser.add_argument("--label", default="", help="suffix for the result file, e.g. emuoverrun")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Not asyncio.run(): on exit it waits up to 300 s for worker threads, and a thread
    # stuck in FlushFileBuffers or a blocking write cannot be cancelled.
    loop = asyncio.new_event_loop()
    exit_code = 2
    try:
        exit_code = loop.run_until_complete(run_all(args))
    except KeyboardInterrupt:
        print("interrupted")
    except Exception:
        traceback.print_exc()
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)


if __name__ == "__main__":
    main()
