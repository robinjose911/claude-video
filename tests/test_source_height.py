"""Source height is derived from the requested frame width, not fixed at 720p.

The old hardcoded `height<=720` was invisible and unconditional. Lifting it
globally would be worse: measured on a real video, a 1080p pull is ~75% larger
(70MB vs 40MB) and indistinguishable at a 1024px frame width, because the
frames are downscaled anyway. The cap only binds once the requested frame width
approaches the source width, so it is raised from the resolution instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts"))
import download  # noqa: E402

URL = "https://www.youtube.com/watch?v=example"


def test_default_resolution_still_uses_720p():
    """The common case must not get more expensive."""
    assert download.height_for_resolution(512) == 720


def test_720p_covers_everything_it_can_supply_natively():
    # A 720p source is 1280px wide, so any frame up to that needs nothing more.
    for resolution in (512, 640, 1024, 1280):
        assert download.height_for_resolution(resolution) == 720


def test_cap_rises_once_the_frame_exceeds_the_source_width():
    assert download.height_for_resolution(1600) == 1080
    assert download.height_for_resolution(1920) == 1080
    assert download.height_for_resolution(2560) == 1440


def test_never_exceeds_the_ladder():
    assert download.height_for_resolution(99999) == download.HEIGHT_LADDER[-1]


def test_format_string_tracks_the_cap():
    assert "height<=720" in download.video_format(720)
    assert "height<=1440" in download.video_format(1440)


def test_cache_key_separates_source_heights(tmp_path):
    """A 1080p run must not be served the cached 720p file."""
    a = download.cache_dir_for(URL, audio_only=False, root=tmp_path, max_height=720)
    b = download.cache_dir_for(URL, audio_only=False, root=tmp_path, max_height=1080)
    assert a != b


def test_audio_key_ignores_height(tmp_path):
    """Audio has no height; the key must not fragment over it."""
    a = download.cache_dir_for(URL, audio_only=True, root=tmp_path, max_height=720)
    b = download.cache_dir_for(URL, audio_only=True, root=tmp_path, max_height=2160)
    assert a == b
