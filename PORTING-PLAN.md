# Porting plan

Working backlog for this fork. Upstream ([bradautomates/claude-video](https://github.com/bradautomates/claude-video))
has never merged a PR, so useful fixes are cherry-picked here instead. This file records
what was evaluated, what landed, and what was rejected **with the evidence**, so nothing
gets re-litigated later.

Optimised for one workflow: **watch → check → summarise → ask follow-ups**, on macOS.

---

## In progress — 2026-09-20

### Environment (not code)
- [x] ~~`brew upgrade yt-dlp`~~ — **not needed.** Installed 2026.8.19 already equals brew
      stable *and* PyPI latest. The "32 days old" figure was the age of the latest release,
      not a stale install. Also learned the active yt-dlp was pip-installed into Homebrew's
      Python, shadowing a stale March brew keg.
- [x] Install `curl_cffi` — done via `uv tool install "yt-dlp[default,curl-cffi]"` (35 MB,
      isolated in `~/.local/bin`, which already wins PATH). Impersonation went from every
      target "(unavailable)" to Chrome-133/136 Macos-15 and Safari 17-18 iOS. Upgrades are
      now `uv tool upgrade yt-dlp`, which is the real protection against YouTube changes.
- [x] Re-verify a real download — `/watch` exit 0, 144 keyframe candidates, 302 caption
      segments, **0 impersonation warnings** (previously one on every single download).
      Note: hit one transient 403 mid-test; proved it was YouTube throttling, not the new
      install, by downloading the same format successfully with both binaries.

### Ports
- [x] **#236** — flag transcript proper nouns as unverified (@gth-spec, 2 lines)
      Validated hard: "TypeSafe", "Diogo", "Almeida", "Vercel" occur **0 times** in the real
      caption track, yet all were reported this session — they were legible only from frames.
      A `--detail transcript` run could not have spelled them at all.
- [x] **#221** — prefer human-authored captions over auto-generated (@oheewono, 49 lines)
      Ported, **plus our own fix**: its auto-track ordering put bare `en` ahead of `en-orig`,
      which on a non-English video swaps the original transcript for a machine translation.
      Reversed it. Verified `en` and `en-orig` are byte-identical (107504b) on English video,
      so no cost. Added the 5 tests the PR shipped without.

### Wrap-up
- [x] Full test suite green — **97 passed**
- [x] CREDITS.md updated (@gth-spec, @oheewono)
- [x] Commit, push, bump version → 0.2.2
- [ ] `/plugin update watch@claude-video` — **Robin runs this**; managed install tracks this fork
- [x] Thanked @gth-spec (#236), @oheewono (#221) and @charles98601-sg (#235) on their upstream PRs

---

## Backlog — evaluated, worth doing, not yet started

| PR | Lines | Why it matters here |
|---|---|---|
| #228 | 483 | Explain a 403 and keep the transcript when only the video stream fails. Same partial-success philosophy as our own extraction guard. Needs careful review — largest of the shortlist. |
| #58  | 36  | Warn when yt-dlp is stale. (#227 does the same in 346 lines — prefer the small one unless review says otherwise.) |

### Our own change, not a port
- [ ] **Lift the hardcoded 720p cap.** `download.py:126` pins `bv*[height<=720]`. Slide-heavy
      videos are unreadable at that source resolution even after bumping `--resolution`.
      Upstream #215 fixes it but drags in 2096 lines across 15 files — write our own
      configurable cap in ~5 lines instead.

---

## Rejected — with evidence, do not revisit without new information

| Area | PRs | Why not |
|---|---|---|
| Windows / encoding | ~35 | macOS only. |
| Local Whisper backends | ~10 | OpenAI key already configured; captions cover most videos. Only worth it for offline/privacy. |
| Non-English captions | ~8 | Content watched is English. Revisit if that changes. |
| HTML entities in VTT (#124) | 1 | Checked the real caption track: **0 entity occurrences**. |
| Scene-cluster fallback (#210) | 1 | Needs candidates ≫ cap to bite. Measured: 33 candidates against a cap of 100. Nothing is being evicted. |
| Whisper hallucination flag (#223) | 1 | Only fires on the Whisper path; captions exist for this content. |
| AssemblyAI / Deepgram / DashScope / TwelveLabs | 4+ | New third-party dependencies, no gain over the current setup. |

---

## Done

- [x] ffmpeg 8+ `-vsync` → `-fps_mode` (ours) — upstream had ~28 unmerged PRs for this
- [x] Graceful degrade when frame extraction fails (ours) — no upstream equivalent
- [x] **#214** cross-provider API key leak (@nbkwabi) — was live: `--whisper groq` posted the OpenAI key to api.groq.com
- [x] **#225** rolling-caption dedupe (@OpenClawLinda) — ~50% of every auto-caption transcript was duplicated
- [x] **#226** uniform sampling spread (@OpenClawLinda) — `--fps 2 --max-frames 6` covered 2.5s of a 16-minute video
- [x] **#236** proper nouns unverified (@gth-spec) — names absent from captions entirely; frames are the only source
- [x] **#221** human-authored captions (@oheewono) + our fix: `en-orig` must outrank translated `en`
- [x] **#235** download cache (@charles98601-sg) + our fixes: cache hits kept dropping the #221 caption
      preference, and the key ignored the media format so the queued 720p-cap lift would have been
      served stale files. Measured 16.2s cold → 8.7s warm.
