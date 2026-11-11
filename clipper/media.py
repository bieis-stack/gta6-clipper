"""Leitura de metadados de vídeo com o ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


class MediaError(Exception):
    pass


@dataclass(frozen=True)
class MediaInfo:
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool


def probe(path: Path) -> MediaInfo:
    command = [
        "ffprobe", "-v", "error", "-of", "json", "-show_streams", "-show_format", str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaError(f"não foi possível correr o ffprobe: {error}") from None
    if result.returncode != 0:
        raise MediaError(f"ficheiro de vídeo ilegível: {Path(path).name}")
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
        fps = float(Fraction(rate)) if not rate.startswith("0/") else float(
            Fraction(video.get("r_frame_rate", "30/1"))
        )
        duration = float(data.get("format", {}).get("duration") or video.get("duration"))
        return MediaInfo(
            width=int(video["width"]),
            height=int(video["height"]),
            duration=duration,
            fps=fps,
            has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        )
    except (StopIteration, KeyError, TypeError, ValueError, ZeroDivisionError):
        raise MediaError(f"o ficheiro não tem uma faixa de vídeo válida: {Path(path).name}") from None
