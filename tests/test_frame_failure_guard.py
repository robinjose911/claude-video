"""An ffmpeg failure must degrade to transcript-only, never abort the run.

Upstream raised SystemExit out of the extraction helpers with nothing catching
it in watch.py, so any ffmpeg incompatibility (see the -vsync removal in
ffmpeg 9) killed the process before the report was printed — losing the
transcript too, even though transcription had already succeeded.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

WATCH = Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts" / "watch.py"

# Stands in for any ffmpeg that rejects the arguments we build.
FAKE_FFMPEG = "#!/bin/sh\necho \"Unrecognized option 'vsync'.\" >&2\nexit 1\n"


def _run_with_broken_ffmpeg(clip: Path, tmp_path: Path, *args: str):
    """Run watch.py with a shim ffmpeg that always fails, real ffprobe intact."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    shim = bin_dir / "ffmpeg"
    shim.write_text(FAKE_FFMPEG)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)

    env = dict(os.environ)
    env.pop("WATCH_DETAIL", None)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [sys.executable, str(WATCH), str(clip), "--no-whisper", *args],
        capture_output=True, text=True, env=env,
    )


def test_scene_engine_failure_still_reports(cut_clip: Path, tmp_path: Path):
    proc = _run_with_broken_ffmpeg(cut_clip, tmp_path, "--detail", "balanced")
    assert proc.returncode == 0, proc.stderr
    assert "# watch: video report" in proc.stdout
    assert "extraction FAILED" in proc.stdout
    assert "No frames extracted" in proc.stdout


def test_keyframe_engine_failure_still_reports(cut_clip: Path, tmp_path: Path):
    proc = _run_with_broken_ffmpeg(cut_clip, tmp_path, "--detail", "efficient")
    assert proc.returncode == 0, proc.stderr
    assert "extraction FAILED" in proc.stdout


def test_cue_frame_failure_still_reports(cut_clip: Path, tmp_path: Path):
    proc = _run_with_broken_ffmpeg(cut_clip, tmp_path, "--timestamps", "0:01")
    assert proc.returncode == 0, proc.stderr
    assert "extraction FAILED" in proc.stdout


def test_failure_names_the_cause(cut_clip: Path, tmp_path: Path):
    """The report must say what broke — a silent empty Frames list is the bug."""
    proc = _run_with_broken_ffmpeg(cut_clip, tmp_path, "--detail", "balanced")
    assert "vsync" in proc.stdout
    assert "frame extraction failed" in proc.stderr
