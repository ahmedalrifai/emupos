import subprocess
import sys

import pytest

from emupos.transports.keyboard import focus

WARP = "/Applications/Warp.app/Contents/MacOS/stable"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def test_outermost_bundle() -> None:
    assert focus.outermost_bundle(WARP) == "/Applications/Warp.app"
    helper = "/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper.app/Contents/MacOS/Code Helper"
    assert focus.outermost_bundle(helper) == "/Applications/Visual Studio Code.app"
    assert focus.outermost_bundle("/bin/zsh") is None


def test_terminal_that_ran_the_command_is_focused() -> None:
    ancestors = [(500, "/bin/zsh"), (400, WARP), (1, "/sbin/launchd")]

    assert focus.matching_terminal(400, "/Applications/Warp.app", ancestors) == "Warp"


def test_same_terminal_bundle_through_a_helper_process() -> None:
    # iTerm2 runs shells under a server process inside its bundle, not under the window process.
    server = "/Applications/iTerm.app/Contents/MacOS/iTermServer-3.5"
    ancestors = [(500, "/bin/zsh"), (450, server)]

    assert focus.matching_terminal(300, "/Applications/iTerm.app", ancestors) == "iTerm"


@pytest.mark.parametrize(
    "terminal",
    [
        "/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",
        "/Applications/iTerm.app/Contents/MacOS/iTerm2",
        "/Applications/Warp.app/Contents/MacOS/stable",
        "/Applications/Ghostty.app/Contents/MacOS/ghostty",
        "/Applications/kitty.app/Contents/MacOS/kitty",
        "/Applications/Alacritty.app/Contents/MacOS/alacritty",
        "/Applications/WezTerm.app/Contents/MacOS/wezterm-gui",
        "/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
        "/Applications/PyCharm.app/Contents/MacOS/pycharm",
    ],
)
def test_any_macos_terminal_running_the_command_is_recognised(terminal: str) -> None:
    ancestors = [(501, "/bin/zsh"), (500, "/usr/bin/login"), (400, terminal)]

    assert focus.matching_terminal(400, focus.outermost_bundle(terminal), ancestors) is not None
    assert focus.matching_terminal(900, focus.outermost_bundle(CHROME), ancestors) is None


def test_inside_tmux_the_client_terminal_is_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    # The shell (70) descends from the tmux server (60); the client (90) runs inside Warp (80).
    parents = {70: (60, "tmux"), 60: (1, "tmux"), 90: (80, "tmux"), 80: (1, WARP)}

    def which(_name: str) -> str:
        return "/opt/homebrew/bin/tmux"

    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="90\n")

    monkeypatch.setenv("TMUX", "default,60,0")
    monkeypatch.setattr(focus.shutil, "which", which)
    monkeypatch.setattr(focus.subprocess, "run", run)

    shell = focus._ancestors(70, parents.__getitem__)  # pyright: ignore[reportPrivateUsage]
    client = focus._tmux_client_ancestors(parents.__getitem__)  # pyright: ignore[reportPrivateUsage]

    assert focus.matching_terminal(80, None, shell) is None  # the shell alone never reaches Warp
    assert focus.matching_terminal(80, "/Applications/Warp.app", shell + client) == "Warp"


def test_another_app_is_focused() -> None:
    ancestors = [(500, "/bin/zsh"), (400, WARP)]

    assert focus.matching_terminal(900, focus.outermost_bundle(CHROME), ancestors) is None


def test_x11_terminal_matches_by_process_id() -> None:
    ancestors = [(700, "bash"), (650, "gnome-terminal-")]

    assert focus.matching_terminal(650, None, ancestors) == "gnome-terminal-"
    assert focus.matching_terminal(999, None, ancestors) is None


def test_an_unknown_answer_never_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> str | None:
        raise OSError("no display")

    monkeypatch.setattr(focus, "_macos_terminal_with_focus", broken)
    monkeypatch.setattr(focus, "_x11_terminal_with_focus", broken)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    assert focus.terminal_with_focus() is None


@pytest.mark.skipif(sys.platform != "darwin", reason="reads the real window list on macOS")
def test_macos_query_runs_without_error() -> None:
    result = focus.terminal_with_focus()  # focus depends on the machine; only the call is checked

    assert result is None or isinstance(result, str)
