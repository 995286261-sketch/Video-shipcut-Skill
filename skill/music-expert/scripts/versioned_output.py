"""Versioned artifact naming — issues ⑧/⑬.

Echo/card artifacts must never silently overwrite a previously presented file:
scan `<prefix>-v0.N<suffix>` in the directory and hand back the next version.
Callers embed the returned version string in the document header so the card,
the file name and the on-disk evidence stay in lockstep.
"""
from __future__ import annotations

import re
from pathlib import Path


def next_versioned(directory: Path, prefix: str, suffix: str) -> tuple[Path, str]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(prefix)}-v0\.(\d+){re.escape(suffix)}$")
    highest = 0
    for entry in directory.iterdir():
        match = pattern.match(entry.name)
        if match:
            highest = max(highest, int(match.group(1)))
    version = f"v0.{highest + 1}"
    return directory / f"{prefix}-{version}{suffix}", version
