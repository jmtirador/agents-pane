"""The version in the code, the changelog and the CLI agree."""

import os
import re
import subprocess
import sys

from cockpit import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def released_versions():
    with open(os.path.join(ROOT, "CHANGELOG.md")) as f:
        return re.findall(r"^## \[(\d+\.\d+\.\d+)\]", f.read(), re.M)


def test_the_newest_changelog_entry_is_the_code_version():
    assert released_versions()[0] == __version__


def test_versions_go_down_the_changelog():
    numbers = [tuple(int(n) for n in v.split(".")) for v in released_versions()]
    assert numbers == sorted(numbers, reverse=True)


def test_the_cli_prints_the_version():
    out = subprocess.run([sys.executable, "-m", "cockpit", "--version"], capture_output=True, text=True, cwd=ROOT)
    assert out.stdout.strip() == __version__
