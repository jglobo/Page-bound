from __future__ import annotations

from pathlib import Path
import re

from .model import Page

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}


def natural_key(value: str):
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r"(\d+)", value.replace("\\", "/")))


def discover(inputs: list[str], progress=None, cancelled=None) -> list[Page]:
    found: dict[str, Path] = {}
    for raw in inputs:
        if cancelled and cancelled():
            break
        root = Path(raw)
        paths = root.rglob("*") if root.is_dir() else (root,)
        for path in paths:
            if cancelled and cancelled():
                break
            if path.is_file() and path.suffix.lower() in SUPPORTED:
                resolved = path.resolve()
                found[str(resolved).casefold()] = resolved
                if progress and len(found) % 25 == 0:
                    progress(len(found))
    return [Page(str(path)) for path in sorted(found.values(), key=lambda p: natural_key(str(p)))]
