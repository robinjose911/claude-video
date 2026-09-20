"""transcribe_video itself must never cross provider keys.

Upstream PR #214 (nbkwabi) fixed the bug, but its tests only exercise
load_api_key() — which was already correct. They pass against the unpatched
source, so they do not actually guard the one-line fix in transcribe_video.
These tests drive transcribe_video and assert on the request that would be
sent; urlopen is stubbed, so nothing leaves the machine.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts"))
import whisper  # noqa: E402


@pytest.fixture
def sent(tmp_path, monkeypatch):
    """Capture what would be POSTed. Returns a dict, empty if no call was made."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"not really audio")
    monkeypatch.setattr(whisper, "extract_audio", lambda video, out: audio)

    captured: dict = {}

    def fake_urlopen(request, *args, **kwargs):
        captured["url"] = request.full_url
        captured["key"] = request.headers.get("Authorization", "").replace("Bearer ", "")
        raise AssertionError(f"request was built for {request.full_url} — see captured")

    monkeypatch.setattr(whisper, "urlopen", fake_urlopen)
    return captured


def _run(tmp_path, backend):
    with pytest.raises(SystemExit) as exc:
        whisper.transcribe_video("video.mp4", tmp_path / "out.mp3", backend=backend)
    return str(exc.value)


def test_forcing_groq_does_not_post_the_openai_key(sent, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-only")
    message = _run(tmp_path, "groq")
    assert not sent, f"a request was built with {sent.get('key','')[:3]}… to {sent.get('url')}"
    assert "No Whisper API key" in message


def test_forcing_openai_does_not_post_the_groq_key(sent, tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-groq-only")
    message = _run(tmp_path, "openai")
    assert not sent, f"a request was built with {sent.get('key','')[:3]}… to {sent.get('url')}"
    assert "No Whisper API key" in message


def test_matching_key_is_still_used(sent, tmp_path, monkeypatch):
    """The guard must not break the normal path."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-groq-only")
    with pytest.raises(AssertionError):
        whisper.transcribe_video("video.mp4", tmp_path / "out.mp3", backend="groq")
    assert "api.groq.com" in sent["url"]
    assert sent["key"] == "gsk-groq-only"
