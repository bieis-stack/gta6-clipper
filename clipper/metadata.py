"""Título e descrição para publicação."""

from __future__ import annotations

from clipper.models import Clip

ELLIPSIS = "…"


def build_title(clip_title: str, streamer_name: str, tag: str, max_len: int = 100) -> str:
    text = " ".join(clip_title.split())
    credit = " ".join(part for part in (streamer_name.strip(), tag.strip()) if part)
    if not text:
        return credit[:max_len]
    suffix = f" | {credit}" if credit else ""
    room = max_len - len(suffix)
    if len(text) > room:
        text = text[: max(room - 1, 0)].rstrip() + ELLIPSIS
        text = text[-room:] if room > 0 else ""
    return (text + suffix)[:max_len]


def build_description(clip: Clip, hashtags: tuple[str, ...]) -> str:
    lines = [
        f"🎥 {clip.broadcaster_name} → https://twitch.tv/{clip.broadcaster_login}",
        f"Clip: {clip.url}",
    ]
    if hashtags:
        lines += ["", " ".join(hashtags)]
    return "\n".join(lines)
