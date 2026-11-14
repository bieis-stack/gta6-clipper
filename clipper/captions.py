"""Transcrição do áudio e geração das legendas em formato ASS."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from clipper.media import probe

SAMPLE_RATE = 16000
FONT = "Anton"
TITLE_SECONDS = 3.0
MIN_CUE_SECONDS = 0.3

_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{FONT},112,&H0000FFFF,&H0000FFFF,&H1A000000,&H1A000000,0,0,0,0,100,100,0,0,3,16,0,5,60,60,0,1
Style: Caption,{FONT},90,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1
Style: Credit,{FONT},36,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,3,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str
    words: tuple[Word, ...] = ()  # vazio: mostrar o texto sem realce palavra a palavra


HIGHLIGHT = "{\\c&H00FFFF&\\fscx112\\fscy112}"  # amarelo e ligeiramente maior
POP_IN = "{\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}"  # o grupo cresce ao aparecer


_model = None


class TranscriptionError(Exception):
    pass


def load_audio(video: Path) -> np.ndarray:
    """Áudio do vídeo em mono, 16 kHz, float32 — o formato que o Whisper espera.

    Descodificado pelo ffmpeg, para não depender do descodificador interno do
    faster-whisper, que é incompatível com versões recentes do PyAV.
    """
    command = [
        "ffmpeg", "-v", "error", "-i", str(video),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-",
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise TranscriptionError(f"não foi possível ler o áudio de {Path(video).name}")
    return np.frombuffer(result.stdout, dtype=np.float32)


def transcribe(video: Path) -> list[Word]:
    """Palavras ditas no vídeo, com tempos. Lista vazia se não houver fala."""
    if not probe(video).has_audio:
        return []
    audio = load_audio(video)
    if audio.size == 0:
        return []
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = _model.transcribe(audio, word_timestamps=True, vad_filter=True)
    return [
        Word(float(word.start), float(word.end), word.word)
        for segment in segments
        for word in (segment.words or [])
    ]


def group_words(
    words: list[Word], max_words: int = 3, max_gap: float = 0.6, max_chars: int = 20
) -> list[Cue]:
    groups: list[list[Word]] = []
    for word in words:
        text = word.text.strip().upper()
        if not text:
            continue
        word = Word(word.start, word.end, text)
        current = groups[-1] if groups else None
        starts_new = (
            current is None
            or len(current) >= max_words
            or word.start - current[-1].end > max_gap
            or len(" ".join(w.text for w in current)) + 1 + len(text) > max_chars
        )
        if starts_new:
            groups.append([word])
        else:
            current.append(word)

    cues = []
    for index, group in enumerate(groups):
        start = group[0].start
        end = max(group[-1].end, start + MIN_CUE_SECONDS)
        if index + 1 < len(groups):
            end = min(end, max(groups[index + 1][0].start, start))
        cues.append(Cue(start, end, " ".join(w.text for w in group), tuple(group)))
    return cues


def escape_ass(text: str) -> str:
    """Neutraliza o que o formato ASS interpretaria como comandos."""
    text = text.replace("{", "(").replace("}", ")").replace("\\", "/")
    return " ".join(text.split())


def _time(seconds: float) -> str:
    centis = max(int(round(seconds * 100)), 0)
    hours, rest = divmod(centis, 360000)
    minutes, rest = divmod(rest, 6000)
    secs, centis = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _event(start: float, end: float, style: str, y: int, text: str, *, raw: bool = False) -> str:
    body = text if raw else escape_ass(text)
    return f"Dialogue: 0,{_time(start)},{_time(end)},{style},,0,0,0,,{{\\pos(540,{y})}}{body}\n"


def _word_events(cue: Cue, offset: float, duration: float, y: int) -> list[str]:
    """Um evento por palavra: o grupo inteiro, com a palavra dita em destaque."""
    texts = [escape_ass(word.text) for word in cue.words]
    events = []
    for index, word in enumerate(cue.words):
        start = cue.start if index == 0 else word.start
        end = cue.words[index + 1].start if index + 1 < len(cue.words) else cue.end
        start, end = start + offset, min(max(end, start) + offset, duration)
        if start >= duration or end <= start:
            continue
        parts = [
            f"{HIGHLIGHT}{text}{{\\r}}" if position == index else text
            for position, text in enumerate(texts)
        ]
        prefix = POP_IN if index == 0 else ""
        events.append(_event(start, end, "Caption", y, prefix + " ".join(parts), raw=True))
    return events


def build_ass(
    cues: list[Cue],
    *,
    title: str,
    credit: str,
    title_y: int,
    caption_y: int,
    credit_y: int,
    duration: float,
    offset: float = 0.0,
) -> str:
    """Legendas do vídeo final. `offset` atrasa as legendas (flash-forward à frente do clip)."""
    events = []
    if escape_ass(title):
        events.append(_event(0, min(TITLE_SECONDS, duration), "Title", title_y, title))
    if escape_ass(credit):
        events.append(_event(0, duration, "Credit", credit_y, credit))
    for cue in cues:
        if not escape_ass(cue.text):
            continue
        if cue.words and all(escape_ass(word.text) for word in cue.words):
            events.extend(_word_events(cue, offset, duration, caption_y))
        elif cue.start + offset < duration:
            end = min(cue.end + offset, duration)
            events.append(_event(cue.start + offset, end, "Caption", caption_y, cue.text))
    return _HEADER + "".join(events)
