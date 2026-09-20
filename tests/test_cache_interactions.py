"""Where the download cache (#235) meets the caption preference (#221).

Neither upstream PR knew about the other, so their combination is untested
there. Both bugs below were live after a clean cherry-pick of both.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts"))
import download  # noqa: E402

URL = "https://www.youtube.com/watch?v=example"


def _entry(tmp_path: Path, manual: list[str]) -> Path:
    """A populated cache entry: a real video file plus two caption tracks."""
    d = tmp_path / "entry"
    d.mkdir()
    (d / "video.mp4").write_bytes(b"not empty")
    for lang in ("en", "en-orig", "de"):
        (d / f"video.{lang}.vtt").write_text("WEBVTT\n", encoding="utf-8")
    (d / "video.info.json").write_text(
        json.dumps({"subtitles": {m: [{}] for m in manual}, "title": "t"}), encoding="utf-8"
    )
    return d


def test_cache_hit_keeps_the_human_authored_caption(tmp_path):
    """A cache hit must not fall back to auto-track ranking.

    Regression: _cached_download called _pick_subtitle(out_dir) with no manual
    language set, so every cache hit silently preferred an auto track even when
    a human-authored one sat right next to it.
    """
    d = _entry(tmp_path, manual=["de"])
    hit = download._cached_download(d)
    assert hit is not None and hit["cached"] is True
    assert Path(hit["subtitle_path"]).name == "video.de.vtt"


def test_cache_hit_still_prefers_orig_over_translated(tmp_path):
    d = _entry(tmp_path, manual=[])
    hit = download._cached_download(d)
    assert Path(hit["subtitle_path"]).name == "video.en-orig.vtt"


def test_media_format_is_part_of_the_cache_key(monkeypatch, tmp_path):
    """Changing the format spec must not serve the previously cached file.

    The key was url + audio/video only, so any change to what gets downloaded
    would have reused the old media for the same URL indefinitely.
    """
    before = download.cache_dir_for(URL, audio_only=False, root=tmp_path)
    monkeypatch.setattr(download, "video_format", lambda h=None: "bv*[height<=1080]+ba/b")
    after = download.cache_dir_for(URL, audio_only=False, root=tmp_path)
    assert before != after


def test_audio_and_video_keys_still_differ(tmp_path):
    a = download.cache_dir_for(URL, audio_only=True, root=tmp_path)
    v = download.cache_dir_for(URL, audio_only=False, root=tmp_path)
    assert a != v


def test_key_is_stable_across_calls(tmp_path):
    a = download.cache_dir_for(URL, audio_only=False, root=tmp_path)
    b = download.cache_dir_for(URL, audio_only=False, root=tmp_path)
    assert a == b
