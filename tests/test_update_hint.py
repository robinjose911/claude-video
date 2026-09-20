"""The upgrade hint must name the tool that actually manages the install.

Upstream PR #228 matched against shutil.which()'s result. Both uv and pipx
place a symlink in ~/.local/bin and keep the real venv elsewhere, so that
string identifies neither: a uv install was told to run `yt-dlp -U`, which
cannot update a managed venv, and pipx fell through its own check. A wrong
command here is worse than no hint, since the message appears exactly when
someone is already stuck.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts"))
import download  # noqa: E402


def _install(tmp_path: Path, real_rel: str) -> Path:
    """A symlink in a bin dir pointing at a real binary elsewhere, as uv/pipx do."""
    real = tmp_path / real_rel
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text("#!/bin/sh\n")
    link_dir = tmp_path / ".local" / "bin"
    link_dir.mkdir(parents=True, exist_ok=True)
    link = link_dir / "yt-dlp"
    link.symlink_to(real)
    return link


@pytest.mark.parametrize("real_rel,expected", [
    (".local/share/uv/tools/yt-dlp/bin/yt-dlp", "uv tool upgrade yt-dlp"),
    (".local/share/pipx/venvs/yt-dlp/bin/yt-dlp", "pipx upgrade yt-dlp"),
    ("opt/homebrew/Cellar/yt-dlp/1.0/bin/yt-dlp", "brew upgrade yt-dlp"),
])
def test_hint_matches_the_real_target(monkeypatch, tmp_path, real_rel, expected):
    link = _install(tmp_path, real_rel)
    monkeypatch.setattr(download.shutil, "which", lambda _: str(link))
    assert download._update_hint() == expected


def test_unknown_layout_falls_back(monkeypatch, tmp_path):
    real = tmp_path / "somewhere" / "yt-dlp"
    real.parent.mkdir(parents=True)
    real.write_text("#!/bin/sh\n")
    monkeypatch.setattr(download.shutil, "which", lambda _: str(real))
    assert "yt-dlp -U" in download._update_hint()


def test_missing_binary_does_not_crash(monkeypatch):
    monkeypatch.setattr(download.shutil, "which", lambda _: None)
    assert "yt-dlp -U" in download._update_hint()
