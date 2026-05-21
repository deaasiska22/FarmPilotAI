"""Per-wallet persistent browser profile.

Profiles live under ``settings.browser.profiles_dir / <label>``. We reuse them
across runs so logged-in sessions, cookies, IndexedDB, and the encrypted
extension keystore survive process restarts.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class BrowserProfile:
    """Filesystem-backed Chromium user data directory."""

    label: str
    root: Path

    @classmethod
    def for_label(cls, label: str, profiles_dir: Path) -> BrowserProfile:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label).strip("_")
        if not safe:
            raise ValueError(f"invalid profile label: {label!r}")
        path = profiles_dir / safe
        path.mkdir(parents=True, exist_ok=True)
        return cls(label=safe, root=path)

    @property
    def user_data_dir(self) -> str:
        return str(self.root)
