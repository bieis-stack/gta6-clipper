"""Texto do gancho e título de publicação, escritos por uma IA gratuita.

Tenta o Gemini (com GEMINI_API_KEY), depois o Pollinations (sem chave). Se
os dois falharem ou responderem mal, o gancho vem de uma lista fixa e o título
fica por conta do título original do clip. Nunca impede a entrega de um clip.
"""

from __future__ import annotations

import json
import logging
import re
import zlib
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
POLLINATIONS_URL = "https://text.pollinations.ai/openai"
TIMEOUT = 20
POLLINATIONS_TIMEOUT = 45  # é gratuito e às vezes lento
MAX_TRANSCRIPT = 1500
HOOK_MIN_WORDS = 2
HOOK_MAX_WORDS = 7
HOOK_MAX_CHARS = 40
TITLE_MAX_CHARS = 70

# Frases neutras: não prometem nada que o clip possa não ter.
FALLBACK_HOOKS = (
    "WAIT FOR IT",
    "WATCH TILL THE END",
    "THE REACTION THOUGH",
    "DON'T BLINK",
    "HE WAS NOT READY",
    "THIS GOT CRAZY FAST",
)

_PROMPT = """You write the on-screen hook and the upload title for a vertical short \
(TikTok / YouTube Shorts) cut from a Twitch stream of {game}.
The audience is 13 to 20 years old and scrolls fast: the hook must make them \
need to see what happens. It must be true to what happens in the clip: no lies, \
no promises the clip does not deliver.

Rules:
- "hook": 2 to 6 words, ALL CAPS, plain words. No emojis, no hashtags, no quotes.
- "title": at most 60 characters, natural English, curiosity, may end with one \
emoji, no hashtags, no streamer name.

Streamer: {streamer}
Title viewers gave the clip: {clip_title}
What the streamer says (speech to text, may have errors): {transcript}

Answer with JSON only: {{"hook": "...", "title": "..."}}"""

_ALLOWED_HOOK = re.compile(r"[^A-Z0-9 '!?.,&$%-]")


@dataclass(frozen=True)
class Texts:
    hook: str
    title: str | None  # None: usar o título original do clip
    source: str  # "gemini", "pollinations" ou "fallback"


def clean_hook(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    words = [word for word in raw.upper().split() if not word.startswith("#")]
    text = _ALLOWED_HOOK.sub("", " ".join(words))
    text = " ".join(text.strip(" '\"").split())
    count = len(text.split())
    if not HOOK_MIN_WORDS <= count <= HOOK_MAX_WORDS or len(text) > HOOK_MAX_CHARS:
        return None
    return text


def clean_title(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    text = " ".join(word for word in raw.split() if not word.startswith("#")).strip(" \"'")
    if not text or len(text) > TITLE_MAX_CHARS:
        return None
    return text


def fallback_hook(clip_id: str) -> str:
    return FALLBACK_HOOKS[zlib.crc32(clip_id.encode("utf-8")) % len(FALLBACK_HOOKS)]


def _parse(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("a resposta não é um objeto JSON")
    return data


def _ask_gemini(prompt: str, api_key: str, model: str, session: requests.Session) -> dict:
    response = session.post(
        GEMINI_URL.format(model=model),
        headers={"x-goog-api-key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return _parse(response.json()["candidates"][0]["content"]["parts"][0]["text"])


def _ask_pollinations(prompt: str, session: requests.Session) -> dict:
    response = session.post(
        POLLINATIONS_URL,
        json={"model": "openai", "messages": [{"role": "user", "content": prompt}]},
        timeout=POLLINATIONS_TIMEOUT,
    )
    response.raise_for_status()
    return _parse(response.json()["choices"][0]["message"]["content"])


def write_texts(
    *,
    transcript: str,
    clip_title: str,
    streamer: str,
    game: str,
    clip_id: str,
    api_key: str,
    model: str,
    session: requests.Session,
) -> Texts:
    words = " ".join(transcript.split())
    prompt = _PROMPT.format(
        game=game,
        streamer=streamer,
        clip_title=" ".join(clip_title.split()) or "(none)",
        transcript=words[:MAX_TRANSCRIPT] or "(nothing understandable)",
    )
    writers = []
    if api_key:
        writers.append(("gemini", lambda: _ask_gemini(prompt, api_key, model, session)))
    writers.append(("pollinations", lambda: _ask_pollinations(prompt, session)))
    for name, ask in writers:
        try:
            data = ask()
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as error:
            # Nunca registar o pedido: leva a chave no cabeçalho.
            log.warning("o %s não escreveu o gancho: %s", name, type(error).__name__)
            continue
        hook = clean_hook(data.get("hook"))
        if hook is None:
            log.warning("o %s deu um gancho inválido: %r", name, data.get("hook"))
            continue
        return Texts(hook=hook, title=clean_title(data.get("title")), source=name)
    return Texts(hook=fallback_hook(clip_id), title=None, source="fallback")
