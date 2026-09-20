#!/usr/bin/env python3
"""Download a video via yt-dlp, or resolve a local file path.

Also fetches subtitles (manual first, then auto-generated) in VTT format so
transcribe.py can parse them without needing Whisper.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".wmv"}



# Downloading is by far the slowest step — tens of seconds and tens of MB for a
# clip whose frames then take ~1s to extract. SKILL.md worked around that by
# asking the model to re-point a second run at the file left in the work dir,
# but the same file says to delete that dir when done, and nothing survives
# across sessions. Keying the download by URL makes the reuse automatic.
AUDIO_FORMAT = "ba/bestaudio"

# Source height is capped because the frames are downscaled anyway: at the
# default 512px frame width a 720p source is already more pixels than the
# frame keeps, and a 1080p pull costs ~75% more bytes for no visible gain
# (measured: 70MB vs 40MB, indistinguishable at 1024px frames). The cap only
# binds once the requested frame width approaches the source width, so it is
# raised from the frame resolution rather than lifted globally.
DEFAULT_MAX_HEIGHT = 720
HEIGHT_LADDER = (720, 1080, 1440, 2160)


def height_for_resolution(resolution: int, floor: int = DEFAULT_MAX_HEIGHT) -> int:
    """Smallest standard source height that can supply `resolution` px natively.

    A 16:9 source of height H is 16/9*H wide, so a frame W px wide needs
    H >= W*9/16 to avoid upscaling. Below that the extra bytes buy nothing.
    """
    needed = (resolution * 9 + 15) // 16
    for height in HEIGHT_LADDER:
        if height >= max(needed, floor):
            return height
    return HEIGHT_LADDER[-1]


def video_format(max_height: int = DEFAULT_MAX_HEIGHT) -> str:
    return f"bv*[height<={max_height}]+ba/b[height<={max_height}]/bv+ba/b"

CACHE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024


def cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base) if base else Path.home() / ".cache") / "watch" / "downloads"


def cache_dir_for(url: str, audio_only: bool, root: Path | None = None,
                  max_height: int = DEFAULT_MAX_HEIGHT) -> Path:
    """Directory holding this URL's download.

    audio_only is part of the key: a `transcript` run fetches audio alone, and
    reusing that for a later frame-extracting run would hand ffmpeg a file with
    no video stream.
    """
    # The format spec is part of the key: raising the resolution cap must not
    # serve a previously cached lower-resolution file for the same URL.
    fmt = AUDIO_FORMAT if audio_only else video_format(max_height)
    payload = f"{url}\x00{'audio' if audio_only else 'video'}\x00{fmt}".encode()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return (root or cache_root()) / digest


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def prune_cache(limit: int = CACHE_LIMIT_BYTES, keep: Path | None = None,
                root: Path | None = None) -> int:
    """Evict least-recently-used entries until the cache fits in ``limit``.

    ``keep`` is never evicted — it is the entry the current run is about to
    use, which would otherwise be the newest and safest thing to delete only in
    the degenerate case where it alone exceeds the limit.
    """
    base = root or cache_root()
    if not base.exists():
        return 0

    entries = []
    for child in base.iterdir():
        if not child.is_dir():
            continue
        try:
            entries.append((child.stat().st_mtime, _dir_size(child), child))
        except OSError:
            continue

    total = sum(size for _, size, _ in entries)
    evicted = 0
    for _, size, child in sorted(entries):
        if total <= limit:
            break
        if keep is not None and child.resolve() == keep.resolve():
            continue
        shutil.rmtree(child, ignore_errors=True)
        total -= size
        evicted += 1
    return evicted


def _cached_download(out_dir: Path) -> dict | None:
    """Return a download result if this directory already holds a usable file."""
    video = _pick_video(out_dir)
    # A run that died mid-download can leave the directory behind. yt-dlp keeps
    # incomplete files under a .part suffix, which _pick_video already ignores,
    # but an empty file would still match — treat it as a miss and re-fetch.
    if video is None or video.stat().st_size == 0:
        return None
    try:  # refresh LRU position
        os.utime(out_dir, None)
    except OSError:
        pass
    info_path = out_dir / "video.info.json"
    return {
        "video_path": str(video),
        # Pass the manual-track set here too, or a cache hit silently drops the
        # human-authored caption preference and falls back to auto ranking.
        "subtitle_path": str(sub) if (sub := _pick_subtitle(
            out_dir, _manual_sub_langs(info_path))) else None,
        "info": _read_info(info_path, "") or {},
        "downloaded": False,
        "cached": True,
    }


def is_url(source: str) -> bool:
    if source.startswith("-"):
        return False
    parsed = urlparse(source)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def resolve_local(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"File not found: {p}")
    if p.suffix.lower() not in VIDEO_EXTS:
        print(
            f"[watch] warning: {p.suffix} is not a known video extension, proceeding anyway",
            file=sys.stderr,
        )
    return {
        "video_path": str(p),
        "subtitle_path": None,
        "info": {"title": p.name, "url": str(p)},
        "downloaded": False,
    }


def _manual_sub_langs(info_path: Path) -> set[str]:
    """Language codes that have a human-authored caption track.

    yt-dlp's info.json lists these under "subtitles"; machine-generated ones
    live under "automatic_captions". The filename alone cannot tell them
    apart, since both are written as video.<lang>.vtt.
    """
    if not info_path.exists():
        return set()
    try:
        raw = json.loads(info_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return set(raw.get("subtitles") or {})


def _pick_subtitle(out_dir: Path, manual_langs: set[str] | None = None) -> Path | None:
    candidates = sorted(out_dir.glob("video*.vtt"))
    if not candidates:
        return None

    manual_langs = manual_langs or set()

    def lang_of(path: Path) -> str:
        # video.en-US.vtt -> en-US
        return path.name[len("video."):-len(".vtt")]

    def rank(path: Path) -> tuple[int, int]:
        lang = lang_of(path)
        # A human-authored track always wins: it is punctuated, speaker-labelled
        # and roughly a third the size of the rolling auto-generated variant.
        manual = 0 if lang in manual_langs else 1
        # Among AUTO tracks, "en-orig" is the source-language track while a bare
        # "en" on a non-English video is YouTube's machine TRANSLATION of it.
        # Preferring "en" there would silently swap an original transcript for a
        # translated one, so "en-orig" ranks first. On an English video the two
        # tracks are byte-identical, so this costs nothing.
        order = {"en-orig": 1, "en": 2, "en-US": 3, "en-GB": 4}.get(lang, 5)
        return (manual, order)

    return min(candidates, key=rank)


def _pick_video(out_dir: Path) -> Path | None:
    for ext in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".opus"):
        for candidate in out_dir.glob(f"video*{ext}"):
            return candidate
    for candidate in out_dir.glob("video.*"):
        if candidate.suffix.lower() in VIDEO_EXTS:
            return candidate
    return None


def _yt_dlp_version() -> str | None:
    """Best-effort `yt-dlp --version` output, or None if it can't be read.

    No network call -- this just execs the already-installed binary. Used only
    to enrich a 403 failure message, so any failure here (missing binary,
    timeout, odd build) degrades to omitting the version rather than raising.
    """
    try:
        proc = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True, timeout=5
        )
        return proc.stdout.strip() or None
    except Exception:
        return None


def _update_hint() -> str:
    """Upgrade command matching how yt-dlp appears to be installed.

    Resolves the symlink before matching. Both uv and pipx put a symlink in
    ~/.local/bin and keep the real venv elsewhere, so inspecting what
    shutil.which() returns identifies neither -- a uv install would be told to
    run `yt-dlp -U`, which cannot update a managed venv, and a pipx install
    would fall through the "pipx" check entirely.
    """
    found = shutil.which("yt-dlp")
    if not found:
        return "yt-dlp -U  (or: pip install -U yt-dlp)"
    try:
        path = str(Path(found).resolve())
    except OSError:
        path = found
    if "uv/tools" in path or "uv\\tools" in path:
        return "uv tool upgrade yt-dlp"
    if "pipx" in path:
        return "pipx upgrade yt-dlp"
    if "Cellar" in path or "homebrew" in path.lower():
        return "brew upgrade yt-dlp"
    return "yt-dlp -U  (or: pip install -U yt-dlp)"


def _download_failure_message(
    output: str, returncode: int, out_dir: Path, subtitle: Path | None
) -> str:
    """Build the error surfaced when yt-dlp produced no video file.

    A bare exit code tells the user nothing actionable. Real incident
    (2026-09-17): a 403 on the media stream was actually a yt-dlp build 2.5
    months stale that had lost YouTube's current client/signature rotation --
    upgrading fixed it with no code change. So a 403/Forbidden in the captured
    output gets the actionable explanation; every other failure keeps the
    original bare message unchanged, since we have no comparable evidence
    about what those mean.
    """
    base = f"yt-dlp did not produce a video file in {out_dir} (exit {returncode})"
    if "403" not in output and "Forbidden" not in output:
        return base
    version = _yt_dlp_version()
    version_note = f" (yt-dlp {version})" if version else ""
    lines = [
        base,
        f"HTTP 403 on the media stream{version_note} -- almost always a yt-dlp that has "
        "fallen behind YouTube's latest signature/client rotation, not a video that's "
        "actually blocked or region-locked.",
        f"Update and retry: {_update_hint()}",
    ]
    if subtitle:
        lines.append(
            f"Captions downloaded fine ({subtitle.name}) -- the transcript is usable even "
            "before you retry the video."
        )
    return "\n".join(lines)


def fetch_captions(url: str, out_dir: Path) -> dict:
    """Fetch metadata and best available VTT captions without downloading video."""
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not installed. Install with: brew install yt-dlp")

    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "video.%(ext)s")
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en.*",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "--no-playlist",
        "--ignore-errors",
        "-o", output_template,
        "--",
        url,
    ]
    subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr)
    info_path = out_dir / "video.info.json"
    subtitle = _pick_subtitle(out_dir, _manual_sub_langs(info_path))
    info = _read_info(info_path, url)
    return {
        "video_path": None,
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": False,
    }


def _read_info(info_path: Path, url: str) -> dict:
    info: dict = {}
    if info_path.exists():
        try:
            raw = json.loads(info_path.read_text(encoding="utf-8"))
            info = {
                "title": raw.get("title"),
                "uploader": raw.get("uploader") or raw.get("channel"),
                "duration": raw.get("duration"),
                "url": raw.get("webpage_url") or url,
            }
        except Exception as exc:
            print(f"[watch] info.json parse failed: {exc}", file=sys.stderr)
            info = {"url": url}
    return info


def download_url(
    url: str,
    out_dir: Path,
    audio_only: bool = False,
    use_cache: bool = False,
    max_height: int = DEFAULT_MAX_HEIGHT,
) -> dict:
    if shutil.which("yt-dlp") is None:
        raise SystemExit("yt-dlp is not installed. Install with: brew install yt-dlp")

    if use_cache:
        hit = _cached_download(out_dir)
        if hit is not None:
            print(f"[watch] reusing cached download: {out_dir}", file=sys.stderr)
            hit["info"] = hit["info"] or {"url": url}
            return hit

    out_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(out_dir / "video.%(ext)s")

    fmt = AUDIO_FORMAT if audio_only else video_format(max_height)
    cmd = [
        "yt-dlp",
        "-N", "8",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en.*",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "--no-playlist",
        "--ignore-errors",
        "-o", output_template,
        "--",
        url,
    ]

    # yt-dlp may exit non-zero if a subtitle variant fails (e.g. 429) even when
    # the video itself downloaded fine. Treat "video file present" as success.
    #
    # Output is captured (rather than piped straight through to the inherited
    # stderr fd) so a failure can be diagnosed -- e.g. a stale yt-dlp getting
    # 403'd by YouTube's latest signature/client rotation -- instead of only
    # surfacing a bare exit code. It's echoed to stderr after the fact so
    # nothing that was visible before is lost, just no longer live-streamed.
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.stdout:
        sys.stderr.write(result.stdout)

    video = _pick_video(out_dir)
    info_path = out_dir / "video.info.json"
    # Keep the manual-caption preference (#221) on this path too.
    subtitle = _pick_subtitle(out_dir, _manual_sub_langs(info_path))
    info = _read_info(info_path, url)

    if video is None:
        failure_message = _download_failure_message(
            result.stdout or "", result.returncode, out_dir, subtitle
        )
        if subtitle is None:
            raise SystemExit(failure_message)
        # The media stream is unavailable (e.g. 403'd) but captions DID come
        # down -- hand back a degraded-but-usable result instead of discarding
        # a complete transcript. watch.py finishes the run in transcript-only
        # mode rather than dying, per the 2026-09-17 incident: subtitles were
        # 272 KB and carried essentially the whole talk while only the media
        # stream failed.
        print(failure_message, file=sys.stderr)
        return {
            "video_path": None,
            "subtitle_path": str(subtitle),
            "info": info or {"url": url},
            "downloaded": False,
            "degraded": True,
            "failure_message": failure_message,
        }

    if use_cache:
        evicted = prune_cache(keep=out_dir)
        if evicted:
            print(f"[watch] cache over limit — evicted {evicted} old download(s)", file=sys.stderr)

    return {
        "video_path": str(video),
        "subtitle_path": str(subtitle) if subtitle else None,
        "info": info or {"url": url},
        "downloaded": True,
    }


def download(
    source: str,
    out_dir: Path,
    audio_only: bool = False,
    use_cache: bool = False,
    max_height: int = DEFAULT_MAX_HEIGHT,
) -> dict:
    if is_url(source):
        return download_url(source, out_dir, audio_only=audio_only, use_cache=use_cache,
                            max_height=max_height)
    return resolve_local(source)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: download.py <url-or-path> <out-dir>", file=sys.stderr)
        raise SystemExit(2)
    result = download(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(result, indent=2))
