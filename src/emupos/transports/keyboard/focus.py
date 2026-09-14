"""Is keyboard focus on the terminal this command runs in? (cli spec, "Scan command")

`emupos scan` types into whatever window has focus. When that is still the terminal that ran the
command, the barcode and its Enter would run as a shell command, so the scan is cancelled.

`terminal_with_focus()` answers with the terminal's name, or None when focus is elsewhere or
cannot be determined (Windows, Wayland, no display, ...): the check never blocks a scan it is
unsure about. Any terminal is recognised, because the check compares the focused app with the
processes this command runs under, not with a list of known terminals.
"""

import ctypes
import importlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

MAX_ANCESTORS = 20


def terminal_with_focus() -> str | None:
    try:
        if sys.platform == "darwin":
            return _macos_terminal_with_focus()
        if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") != "wayland":
            return _x11_terminal_with_focus()
    except Exception:  # an unknown answer must never stop or break a scan
        return None
    return None


# --- pure helpers (tested directly) ------------------------------------------------------------


def outermost_bundle(executable: str) -> str | None:
    """`/Applications/Warp.app/Contents/MacOS/stable` -> `/Applications/Warp.app`."""
    if ".app/" not in executable:
        return None
    return executable[: executable.index(".app/") + len(".app")]


def matching_terminal(
    focused_pid: int, focused_bundle: str | None, ancestors: Iterable[tuple[int, str]]
) -> str | None:
    """The terminal's name when the focused app is one of this process's ancestors.

    `ancestors` are (pid, executable path) pairs. Apps are compared by process id, and on macOS
    also by app bundle, because a terminal's shells may be children of a helper process inside the
    same bundle rather than of the window's own process.
    """
    for pid, executable in ancestors:
        bundle = outermost_bundle(executable)
        if pid == focused_pid or (bundle is not None and bundle == focused_bundle):
            return Path(bundle).stem if bundle else Path(executable).name
    return None


# --- macOS -----------------------------------------------------------------------------------


def _macos_terminal_with_focus() -> str | None:
    quartz: Any = importlib.import_module("Quartz")  # exists on macOS only
    options = quartz.kCGWindowListOptionOnScreenOnly | quartz.kCGWindowListExcludeDesktopElements
    # Windows are listed front to back; the first normal-layer window belongs to the focused app.
    for window in quartz.CGWindowListCopyWindowInfo(options, quartz.kCGNullWindowID) or ():
        if window.get("kCGWindowLayer") == 0:
            pid = int(window["kCGWindowOwnerPID"])
            return matching_terminal(pid, outermost_bundle(_executable(pid)), ps_ancestors())
    return None


def _executable(pid: int) -> str:
    return _ps(pid).partition(" ")[2]


def _ps(pid: int) -> str:
    """`<ppid> <executable path>` for a process, from ps."""
    return subprocess.run(  # noqa: S603 - fixed arguments
        ["/bin/ps", "-o", "ppid=,comm=", "-p", str(pid)],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    ).stdout.strip()


def ps_ancestors() -> list[tuple[int, str]]:
    """(pid, executable) of this process's parents, nearest first, including a tmux client's."""
    return _ancestors(os.getppid(), _ps_parent) + _tmux_client_ancestors(_ps_parent)


def _ps_parent(pid: int) -> tuple[int, str]:
    parent, _, executable = _ps(pid).partition(" ")
    return (int(parent) if parent.isdigit() else 0), executable


def _ancestors(start: int, parent_of: Callable[[int], tuple[int, str]]) -> list[tuple[int, str]]:
    ancestors: list[tuple[int, str]] = []
    pid = start
    for _ in range(MAX_ANCESTORS):
        parent, executable = parent_of(pid)
        ancestors.append((pid, executable))
        if parent <= 1:
            break
        pid = parent
    return ancestors


def _tmux_client_ancestors(parent_of: Callable[[int], tuple[int, str]]) -> list[tuple[int, str]]:
    """Inside tmux the shell descends from the tmux server, not the terminal: follow the client."""
    tmux = shutil.which("tmux")
    if not os.environ.get("TMUX") or tmux is None:
        return []
    client = subprocess.run(  # noqa: S603 - fixed arguments
        [tmux, "display-message", "-p", "#{client_pid}"],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    ).stdout.strip()
    return _ancestors(int(client), parent_of) if client.isdigit() else []


# --- Linux X11 -------------------------------------------------------------------------------


def _x11_terminal_with_focus() -> str | None:
    pid = _x11_active_window_pid()
    if pid is None:
        return None
    ancestors = _ancestors(os.getppid(), _proc_parent) + _tmux_client_ancestors(_proc_parent)
    return matching_terminal(pid, None, ancestors)


def _proc_parent(pid: int) -> tuple[int, str]:
    stat = Path(f"/proc/{pid}/stat").read_text()
    name = stat[stat.index("(") + 1 : stat.rindex(")")]
    return int(stat[stat.rindex(")") + 2 :].split()[1]), name  # field 4 is the parent pid


def _x11_active_window_pid() -> int | None:
    """`_NET_WM_PID` of the window named by the root window's `_NET_ACTIVE_WINDOW`."""
    if not os.environ.get("DISPLAY"):
        return None
    x11 = ctypes.CDLL("libX11.so.6")
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XGetWindowProperty.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
        ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
    ]  # fmt: skip
    x11.XFree.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        return None
    try:
        window = _x11_cardinal(x11, display, x11.XDefaultRootWindow(display), b"_NET_ACTIVE_WINDOW")
        return None if not window else _x11_cardinal(x11, display, window, b"_NET_WM_PID")
    finally:
        x11.XCloseDisplay(display)


def _x11_cardinal(x11: ctypes.CDLL, display: int, window: int, name: bytes) -> int | None:
    atom = x11.XInternAtom(display, name, 1)
    if not atom:
        return None
    kind, width = ctypes.c_ulong(), ctypes.c_int()
    count, remaining = ctypes.c_ulong(), ctypes.c_ulong()
    data = ctypes.POINTER(ctypes.c_ulong)()
    status = x11.XGetWindowProperty(
        display, window, atom, 0, 1, 0, 0,  # AnyPropertyType
        ctypes.byref(kind), ctypes.byref(width), ctypes.byref(count),
        ctypes.byref(remaining), ctypes.byref(data),
    )  # fmt: skip
    try:
        return int(data[0]) if status == 0 and count.value and data else None
    finally:
        if data:
            x11.XFree(data)
