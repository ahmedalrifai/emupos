"""Print one version's section of CHANGELOG.md, for the GitHub Release notes.

    python .github/scripts/changelog_section.py X.Y.Z

release-please writes sections headed `## [X.Y.Z](compare-link) (date)` or `## X.Y.Z (date)`.
"""

import re
import sys
from pathlib import Path


def section(changelog: str, version: str) -> str:
    heading = re.compile(rf"^## \[?{re.escape(version)}\]?[ (]", re.MULTILINE)
    start = heading.search(changelog)
    if start is None:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    body_start = changelog.index("\n", start.start()) + 1
    next_section = re.compile(r"^## ", re.MULTILINE).search(changelog, body_start)
    return changelog[body_start : next_section.start() if next_section else len(changelog)].strip()


if __name__ == "__main__":
    print(section(Path("CHANGELOG.md").read_text(encoding="utf-8"), sys.argv[1]))
