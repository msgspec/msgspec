"""Run stubtest against the installed msgspec package.

Entries that apply to every supported Python version live in
`tests/typing/stubtest_allowlist.txt`. Findings that only exist from a given
version onwards go in `tests/typing/stubtest_allowlist_py<major><minor>_plus.txt`,
and every such file whose version is at or below the running interpreter is
passed too.

stubtest runs without `--ignore-unused-allowlist`, so an entry that stops
matching is reported instead of silently lingering.
"""

import re
import subprocess
import sys
from pathlib import Path

ALLOWLIST_DIR = Path(__file__).parents[1] / "tests" / "typing"
VERSIONED_ALLOWLIST = re.compile(r"^stubtest_allowlist_py(\d)(\d+)_plus\.txt$")


def allowlists():
    yield ALLOWLIST_DIR / "stubtest_allowlist.txt"

    versioned = []
    for path in ALLOWLIST_DIR.iterdir():
        match = VERSIONED_ALLOWLIST.match(path.name)
        if match is not None:
            version = (int(match.group(1)), int(match.group(2)))
            if version <= sys.version_info[:2]:
                versioned.append((version, path))

    for _, path in sorted(versioned):
        yield path


def main():
    command = [sys.executable, "-m", "mypy.stubtest", "msgspec"]
    for allowlist in allowlists():
        command.extend(["--allowlist", str(allowlist)])
    command.extend(sys.argv[1:])
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
