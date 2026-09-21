"""The packaged control page files keep device data as text and load nothing from elsewhere."""

import re
from importlib import resources

import pytest

PAGE = resources.files("emupos.api").joinpath("page")
FILES = ("index.html", "page.js", "page.css")


@pytest.mark.parametrize("name", ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"])
def test_the_script_never_inserts_html(name: str) -> None:
    # Receipt text, scans and client addresses come from whatever connects to a device port (D7).
    assert name not in PAGE.joinpath("page.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("file", FILES)
def test_nothing_is_loaded_from_another_origin(file: str) -> None:
    assert not re.search(r"https?://", PAGE.joinpath(file).read_text(encoding="utf-8"))


def test_no_inline_styles() -> None:
    # The page's policy (default-src 'self') refuses style attributes and <style> elements.
    html = PAGE.joinpath("index.html").read_text(encoding="utf-8")
    script = PAGE.joinpath("page.js").read_text(encoding="utf-8")
    assert not re.search(r"<style|\sstyle=", html)
    assert not re.search(r"""setAttribute\(\s*["']style|["']?style["']?\s*:""", script)
