"""Montagem do vídeo vertical final com o ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from clipper.media import MediaError, MediaInfo, probe
from clipper.models import Rect

OUT_W = 1080
OUT_H = 1920
CAM_H = 768
GAME_H = 1152
FILL_H = 1440
MAX_FPS = 60
MAX_BYTES = 50 * 1024 * 1024
CRF_STEPS = (20, 26, 32)
TIMEOUT = 900


class RenderError(Exception):
    pass


def text_positions(has_facecam: bool) -> dict[str, int]:
    """Alturas (em píxeis do vídeo final) do título, das legendas e do crédito."""
    if has_facecam:
        return {"title_y": 1000, "caption_y": CAM_H, "credit_y": 1880}
    return {"title_y": 120, "caption_y": 1560, "credit_y": 1800}


def _escape(path: Path) -> str:
    """Caminho pronto a usar como valor de opção dentro de um filter_complex.

    Dois níveis de escape: o do valor da opção e o do grafo de filtros.
    """
    text = str(path)
    for char in "\\':":
        text = text.replace(char, "\\" + char)
    for char in "\\'[],;":
        text = text.replace(char, "\\" + char)
    return text


def _fps(info: MediaInfo) -> str:
    fps = min(info.fps, MAX_FPS) if info.fps > 0 else 30
    return f"{fps:.3f}".rstrip("0").rstrip(".")


def build_filter(info: MediaInfo, facecam: Rect | None, ass_path: Path, fonts_dir: Path) -> str:
    finish = (
        f"setsar=1,fps={_fps(info)},"
        f"subtitles=filename={_escape(ass_path)}:fontsdir={_escape(fonts_dir)}[v]"
    )
    if facecam is not None:
        cam = facecam
        return (
            "[0:v]split=2[c][g];"
            f"[c]crop={cam.w}:{cam.h}:{cam.x}:{cam.y},"
            f"scale={OUT_W}:{CAM_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{CAM_H}[cam];"
            f"[g]crop='min(iw,ih*{OUT_W}/{GAME_H})':'min(ih,iw*{GAME_H}/{OUT_W})',"
            f"scale={OUT_W}:{GAME_H}[game];"
            f"[cam][game]vstack,{finish}"
        )
    top = (OUT_H - FILL_H) // 2
    return (
        "[0:v]split=2[b][f];"
        f"[b]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},gblur=sigma=30[bg];"
        f"[f]crop='min(iw,ih*3/4)':'min(ih,iw*4/3)',scale={OUT_W}:{FILL_H}[fg];"
        f"[bg][fg]overlay=0:{top},{finish}"
    )


def render(
    src: Path,
    dst: Path,
    *,
    facecam: Rect | None,
    ass_path: Path,
    fonts_dir: Path,
    max_bytes: int = MAX_BYTES,
) -> None:
    """Escreve em `dst` o vídeo 1080×1920, recomprimindo até caber em `max_bytes`."""
    src, dst = Path(src), Path(dst)
    try:
        info = probe(src)
    except MediaError as error:
        raise RenderError(str(error)) from None
    graph = build_filter(info, facecam, Path(ass_path), Path(fonts_dir))
    dst.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    for crf in CRF_STEPS:
        command = [
            "ffmpeg", "-v", "error", "-y", "-i", str(src),
            "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            dst.unlink(missing_ok=True)
            raise RenderError(f"o ffmpeg demorou demasiado a montar {src.name}") from None
        if result.returncode != 0 or not dst.exists():
            dst.unlink(missing_ok=True)
            detail = result.stderr.strip().splitlines()[-1:] or ["sem detalhe"]
            raise RenderError(f"o ffmpeg falhou a montar {src.name}: {detail[0]}")
        size = dst.stat().st_size
        if size <= max_bytes:
            return
    dst.unlink(missing_ok=True)
    raise RenderError(
        f"{src.name} não cabe em {max_bytes} bytes mesmo com compressão máxima ({size} bytes)"
    )
