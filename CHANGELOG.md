# Changelog

All notable changes to `/watch` are documented here.

## [0.2.3] — 2026-09-20 (fork)

### Added
- **Downloads are cached by URL** (upstream #235, @charles98601-sg). Downloading dominates a
  run; a follow-up question about the same video used to pay for it again. Keyed under
  `~/.cache/watch/downloads`, 2 GB LRU cap, audio-only and full-video kept as separate
  entries. Measured on a 16-minute video: **16.2s cold, 8.7s warm**, identical frame
  selection. `--no-cache` and `--out-dir` opt out.
- **A 403 now explains itself, and a dead video stream no longer discards the transcript**
  (upstream #228, @OpenClawLinda). A bare `HTTP 403` reads like a blocked video when it is
  usually a stale yt-dlp, so the message now says so, reports the installed version and
  prints the matching upgrade command. When only the media stream fails while captions
  succeed, the run completes in transcript-only mode with a loud `NO VIDEO OBTAINED`
  warning instead of dying.
- **`--max-height`**, and the source height cap is now stated in the report.

### Changed
- **The source height cap is derived from `--resolution` instead of pinned at 720p.**
  Measured before changing anything: a 1080p pull is ~75% larger (70 MB vs 40 MB) and
  visually indistinguishable at a 1024px frame width, because frames are downscaled anyway.
  Raising the default would have cost every run for nothing. A 16:9 source of height H is
  16/9·H wide, so the cap now rises only when the requested frame width needs it:
  `512→720p`, `1280→720p`, `1920→1080p`, `2560→1440p`.

### Fixed
- **Cache hits no longer discard the human-authored caption preference.** `_cached_download`
  called `_pick_subtitle()` without the manual-language set, so every hit silently fell back
  to auto-track ranking — an interaction between #235 and #221 that neither author could see.
- **The cache key now includes the media format.** It was URL + audio/video only, so lifting
  the resolution cap would have served the cached 720p file for that URL indefinitely, with a
  perfectly healthy-looking run. The height-cap change above is only safe because of this.
- **The upgrade hint resolves the symlink before matching.** #228 matched against
  `shutil.which()`, but uv and pipx both symlink into `~/.local/bin` and keep the real venv
  elsewhere — so a uv install was told to run `yt-dlp -U`, which cannot update a managed
  venv, and pipx fell through its own check. A wrong command here is worse than no hint,
  since it appears when someone is already stuck.

### Added (tests)
- `test_cache_interactions.py`, `test_source_height.py`, `test_update_hint.py` — 17 tests
  across the three fixes above; each fails against the code it guards.
- Made #228's own 403 test host-independent. It called the real `_update_hint()` and asserted
  against three hard-coded strings, so it passed or failed on how the developer installed
  yt-dlp, and failed outright on a uv install.

**138 tests passing.**

## [0.2.2] — 2026-09-20 (fork)

### Added
- **Proper nouns in transcripts are flagged as unverified** (upstream #236, @gth-spec).
  Captions transcribe phonetically, so names arrive wrong or missing entirely. Measured on
  one real video: "TypeSafe", "Diogo", "Almeida" and "Vercel" appear **zero times** in the
  auto-caption track despite being central to the content — they are only legible from
  frames. The skill now says to confirm names against a frame, and to mark them as
  transcript-only and unverified where no frame does.

### Changed
- **Human-authored caption tracks are preferred over auto-generated ones** (upstream #221,
  @oheewono). Manual tracks are punctuated, speaker-labelled and roughly a third the size
  of the rolling auto-generated variant.
- **Among auto tracks, `en-orig` now outranks a bare `en`.** #221 had this the other way
  round; on a non-English video `en` is YouTube's machine translation while `en-orig` is
  the source-language track, so the original would have been silently replaced by a
  translation. Byte-identical on English videos, so no cost where it does not apply.

### Added (tests)
- `tests/test_subtitle_choice.py` — five tests covering track selection. #221 shipped with
  none; the ordering test fails against its original ranking.

## [0.2.1] — 2026-09-20 (fork)

First release of the [robinjose911](https://github.com/robinjose911/claude-video) fork of
[bradautomates/claude-video](https://github.com/bradautomates/claude-video). Upstream `v0.2.0`
plus the two fixes below; everything else is unchanged.

### Fixed
- **Frame extraction on ffmpeg 8+ (`-vsync` was removed).** `frames.py` passed `-vsync vfr`
  to ffmpeg in both the scene-aware path (`balanced`, `token-burner`) and the keyframe path
  (`efficient`). ffmpeg removed the long-deprecated `-vsync` in favour of `-fps_mode`, so on
  ffmpeg 8/9 both paths died with `Unrecognized option 'vsync'` and **no frames were ever
  extracted**. Now uses `-fps_mode vfr`, which is equivalent and has been supported since
  ffmpeg 5.1. Upstream issues: #99, #117, #126, #143, #161, #163, #174, #180, #195, #229.
- **An ffmpeg failure no longer aborts the whole run.** The extraction helpers raise
  `SystemExit`, and nothing in `watch.py` caught it, so the process exited before printing
  the report — discarding the transcript as well, even when transcription had already
  succeeded. All the user saw was one line of ffmpeg stderr. Frame extraction (both the
  detail engines and `--timestamps` cue frames) is now guarded: on failure `/watch` prints
  the full report with the transcript intact, names the cause in the **Frames** line, and
  exits 0. Not covered by any upstream pull request.

### Added
- `tests/test_frame_failure_guard.py` — four regression tests that shim a failing `ffmpeg`
  onto `PATH` and assert the report still prints, still names the cause, and still exits 0.
  These fail against upstream `v0.2.0` and pass here.

## [0.2.0] — 2026-06-29

### Added
- **`--detail` dial** with four modes — `transcript` (captions only, no frames), `efficient` (fast keyframe pass, cap 50), `balanced` (scene-aware, cap 100, default), and `token-burner` (scene-aware, uncapped). Set the default with `WATCH_DETAIL` in `~/.config/watch/.env`.
- **Frame deduplication** (default on; `--no-dedup` to disable). Before the budget cap, a pass downscales each frame to a 16×16 grayscale thumbnail and drops frames whose mean per-pixel difference from the last *kept* frame is within threshold — so the budget goes to distinct content instead of held slides and static recordings. The **Frames** report line shows how many near-duplicates were dropped.
- **Whisper auto-chunking.** Audio over the 25 MB upload cap is split into evenly sized chunks, transcribed per chunk, with segment timestamps shifted back into source time. Partial failures are tolerated — transcription only fails if *every* chunk fails, so length alone no longer breaks it.
- **`--timestamps T1,T2,…`** — grab a frame at each absolute timestamp; reserved against the cap, and the only frames produced under `--detail transcript`.
- **`--no-whisper`** — disable transcription entirely (frames only).
- pytest suite covering config, dedup, download, fixtures, frames, setup, timestamps, watch, and whisper (no network; ffmpeg-synthesized clips).

### Changed
- **Restructured into a self-contained `skills/watch/` package** so `SKILL.md` and its `scripts/` runtime are siblings in one folder. This fixes installs on Codex, Cursor, Copilot, and other Agent Skills hosts: `npx skills add` now copies the skill as a working unit instead of grabbing the root `SKILL.md` without its scripts.
- **Harness-agnostic path resolution** — `SKILL.md` resolves `$SKILL_DIR` from where it was Read instead of the Claude-Code-only `${CLAUDE_SKILL_DIR}`, so script calls work on every host.
- `/watch` is now derived from `SKILL.md` frontmatter; the separate `commands/watch.md` wrapper was dropped to avoid a duplicate slash command.
- `balanced` now full-decodes to detect every scene cut across the whole video. The previous early-exit was faster but kept only the first cuts and dropped the tail of long videos.
- `token-burner` is exempt from the long-video "sparse scan" warning, since it keeps every scene-change frame.
- `--max-frames` is now an override on top of each mode's default cap, rather than a fixed default of 80.

### Fixed
- Non-Claude installs (`npx skills add`) were dead on arrival — the installer copied `SKILL.md` without the `scripts/` it shells out to. The self-contained package layout resolves this.

### Removed
- `V2_PLAN.md` and `V2_CONCERNS.md` planning docs.

## [0.1.3] — 2026-05-09

### Fixed
- Windows: `video.info.json` is read as UTF-8 (#4). Previously `Path.read_text()` defaulted to cp1252 on Windows and crashed on yt-dlp's UTF-8 output, silently dropping Title/Uploader from the report. Same fix applied to `.env` reads/writes in `whisper.py` and `setup.py`.
- `download.py` now logs info.json parse failures to stderr instead of swallowing them.

### Security
- Hardened subprocess argv against option injection (#2): inserted `--` before the URL in the yt-dlp argv, and tightened `is_url` to reject `-`-prefixed sources and require a non-empty netloc. Resolved video/audio paths to absolute via `Path.resolve()` before passing to `ffmpeg`/`ffprobe`, so a relative path starting with `-` can't be misinterpreted as a flag.

## [0.1.2] — 2026-04-24

### Fixed
- Windows console crash: removed the emoji from the long-video warning in `watch.py`; cp1252 consoles couldn't encode it.
- `setup.py` now prints `winget` / `pip` install commands on Windows instead of "unsupported platform" — matches what the README already promised.

### Changed
- `SKILL.md` notes that on Windows the scripts must be invoked with `python`, not `python3` (the latter is the Microsoft Store stub on Windows).

## [0.1.1] — 2026-04-24

### Fixed
- Added `commands/watch.md` shim so `/watch` is callable when installed as a Claude Code plugin. Without it, the plugin loaded but the skill wasn't exposed as a slash command.
- `scripts/build-skill.sh` now strips `commands/` from the claude.ai `.skill` bundle alongside `hooks/` and `.claude-plugin/`.

## [0.1.0] — 2026-04-24

Initial marketplace release.

### Added
- `/watch <url-or-path> [question]` slash command.
- yt-dlp download with native caption extraction (manual + auto-subs).
- ffmpeg frame extraction with auto-scaled fps (≤2 fps, ≤100 frames, duration-aware budget).
- `--start` / `--end` focused mode with denser frame budget and transcript range filtering.
- Whisper fallback (Groq preferred, OpenAI secondary) for videos without captions.
- `setup.py` preflight: silent `--check`, structured `--json`, and installer that auto-runs `brew install` on macOS.
- Session-start hook that prints a one-line status on first run / partial config.
- `.skill` bundle packaging for claude.ai upload via `scripts/build-skill.sh`.
