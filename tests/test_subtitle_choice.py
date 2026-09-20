"""Which caption track gets picked.

Upstream PR #221 (@oheewono) added the human-authored preference, which is the
important part: a manual track is punctuated, speaker-labelled and roughly a
third the size of the rolling auto-generated one. It shipped without tests, and
its auto-track ordering preferred a bare "en" over "en-orig" — see
test_auto_prefers_orig_over_translated for why that is the wrong way round.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts"))
import download  # noqa: E402


def _tracks(tmp_path: Path, langs: list[str], manual: list[str] | None = None) -> Path:
    for lang in langs:
        (tmp_path / f"video.{lang}.vtt").write_text("WEBVTT\n", encoding="utf-8")
    (tmp_path / "video.info.json").write_text(
        json.dumps({"subtitles": {m: [{}] for m in (manual or [])}}), encoding="utf-8"
    )
    return tmp_path / "video.info.json"


def _pick(tmp_path: Path) -> str:
    info = tmp_path / "video.info.json"
    return download._pick_subtitle(tmp_path, download._manual_sub_langs(info)).name


def test_manual_track_beats_auto(tmp_path: Path):
    _tracks(tmp_path, ["en", "en-orig", "de"], manual=["de"])
    assert _pick(tmp_path) == "video.de.vtt"


def test_manual_english_preferred_when_available(tmp_path: Path):
    _tracks(tmp_path, ["en", "en-orig"], manual=["en"])
    assert _pick(tmp_path) == "video.en.vtt"


def test_auto_prefers_orig_over_translated(tmp_path: Path):
    """On a non-English video a bare "en" auto track is a MACHINE TRANSLATION.

    "en-orig" is the source-language track. Picking "en" would silently hand
    back a translation instead of what was actually said.
    """
    _tracks(tmp_path, ["en", "en-orig"], manual=[])
    assert _pick(tmp_path) == "video.en-orig.vtt"


def test_no_tracks_returns_none(tmp_path: Path):
    (tmp_path / "video.info.json").write_text("{}", encoding="utf-8")
    assert download._pick_subtitle(tmp_path, set()) is None


def test_missing_info_json_does_not_crash(tmp_path: Path):
    (tmp_path / "video.en.vtt").write_text("WEBVTT\n", encoding="utf-8")
    assert download._manual_sub_langs(tmp_path / "nope.json") == set()
    assert download._pick_subtitle(tmp_path, set()).name == "video.en.vtt"
