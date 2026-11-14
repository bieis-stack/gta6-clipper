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
AUDIO_BITRATE = 128_000
MAX_VIDEO_BITRATE = 12_000_000
MIN_VIDEO_BITRATE = 100_000
# (crf, fração do orçamento de bytes a usar). A primeira passagem chega quase
# sempre; a segunda existe para o caso raro de o codificador exceder o teto.
ENCODE_STEPS = ((20, 0.90), (28, 0.65))
TIMEOUT = 240


class RenderError(Exception):
    pass


def text_positions(has_facecam: bool) -> dict[str, int]:
    """Alturas (em píxeis do vídeo final) do título, das legendas e do crédito."""
    # Tudo entre 250 e 1500: o YouTube Shorts e o TikTok tapam o topo e o
    # fundo do vídeo com a sua própria interface.
    if has_facecam:
        return {"title_y": 1000, "caption_y": CAM_H, "credit_y": 1480}
    return {"title_y": 330, "caption_y": 1340, "credit_y": 1480}


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


def _number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _flash_forward(info: MediaInfo, flash: tuple[float, float]) -> str:
    """Grafo que põe o troço `flash` (início, duração) à frente do clip inteiro.

    Produz [src] (vídeo) e, se houver áudio, [a].
    """
    start, length = (_number(value) for value in flash)
    video = (
        "[0:v]split=2[fv][mv];"
        f"[fv]trim=start={start}:duration={length},setpts=PTS-STARTPTS[v1];"
        "[mv]setpts=PTS-STARTPTS[v2];"
    )
    if not info.has_audio:
        return video + "[v1][v2]concat=n=2:v=1:a=0[src];"
    audio = (
        "[0:a]asplit=2[fa][ma];"
        f"[fa]atrim=start={start}:duration={length},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st={_number(max(flash[1] - 0.08, 0))}:d=0.08[a1];"
        "[ma]asetpts=PTS-STARTPTS,afade=t=in:d=0.05[a2];"
    )
    return video + audio + "[v1][a1][v2][a2]concat=n=2:v=1:a=1[src][a];"


def build_filter(
    info: MediaInfo,
    facecam: Rect | None,
    ass_path: Path,
    fonts_dir: Path,
    *,
    flash: tuple[float, float] | None = None,
) -> str:
    finish = (
        f"setsar=1,fps={_fps(info)},"
        f"subtitles=filename={_escape(ass_path)}:fontsdir={_escape(fonts_dir)}[v]"
    )
    head, source = (_flash_forward(info, flash), "[src]") if flash else ("", "[0:v]")
    if facecam is not None:
        cam = facecam
        return head + (
            f"{source}split=2[c][g];"
            f"[c]crop={cam.w}:{cam.h}:{cam.x}:{cam.y},"
            f"scale={OUT_W}:{CAM_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{CAM_H}[cam];"
            f"[g]crop='min(iw,ih*{OUT_W}/{GAME_H})':'min(ih,iw*{GAME_H}/{OUT_W})',"
            f"scale={OUT_W}:{GAME_H}[game];"
            f"[cam][game]vstack,{finish}"
        )
    top = (OUT_H - FILL_H) // 2
    return head + (
        f"{source}split=2[b][f];"
        # Desfoca uma cópia a um quarto do tamanho e só depois amplia: o
        # resultado é o mesmo fundo difuso por uma fração do tempo de cálculo.
        f"[b]scale={OUT_W // 4}:{OUT_H // 4}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W // 4}:{OUT_H // 4},gblur=sigma=8,scale={OUT_W}:{OUT_H}[bg];"
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
    flash: tuple[float, float] | None = None,
) -> None:
    """Escreve em `dst` o vídeo 1080×1920, recomprimindo até caber em `max_bytes`.

    Com `flash` (início, duração), o vídeo abre com esse troço do clip.
    """
    src, dst = Path(src), Path(dst)
    try:
        info = probe(src)
    except MediaError as error:
        raise RenderError(str(error)) from None
    graph = build_filter(info, facecam, Path(ass_path), Path(fonts_dir), flash=flash)
    audio_map = "[a]" if flash and info.has_audio else "0:a?"
    duration = info.duration + (flash[1] if flash else 0)
    dst.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    for crf, share in ENCODE_STEPS:
        # Teto de débito calculado a partir do limite de bytes e da duração,
        # para o ficheiro caber à primeira em vez de codificar várias vezes.
        budget = max_bytes * 8 * share / max(duration, 1.0)
        bitrate = int(min(budget - (AUDIO_BITRATE if info.has_audio else 0), MAX_VIDEO_BITRATE))
        if bitrate < MIN_VIDEO_BITRATE:
            break
        command = [
            "ffmpeg", "-v", "error", "-y", "-i", str(src),
            "-filter_complex", graph, "-map", "[v]", "-map", audio_map,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-maxrate", str(bitrate), "-bufsize", str(bitrate * 2), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", str(AUDIO_BITRATE), "-movflags", "+faststart", str(dst),
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
    raise RenderError(f"{src.name} não cabe em {max_bytes} bytes mesmo com compressão máxima")


def render_cover(
    src: Path,
    dst: Path,
    *,
    facecam: Rect | None,
    ass_path: Path,
    fonts_dir: Path,
    at: float,
) -> None:
    """Capa 1080×1920 em JPG: o fotograma do instante `at`, enquadrado como o vídeo."""
    src, dst = Path(src), Path(dst)
    try:
        info = probe(src)
    except MediaError as error:
        raise RenderError(str(error)) from None
    graph = build_filter(info, facecam, Path(ass_path), Path(fonts_dir))
    dst.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-v", "error", "-y", "-ss", _number(max(at, 0)), "-i", str(src),
        "-filter_complex", graph, "-map", "[v]", "-frames:v", "1", "-q:v", "3", str(dst),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        dst.unlink(missing_ok=True)
        raise RenderError(f"o ffmpeg demorou demasiado a fazer a capa de {src.name}") from None
    if result.returncode != 0 or not dst.exists():
        dst.unlink(missing_ok=True)
        detail = result.stderr.strip().splitlines()[-1:] or ["sem detalhe"]
        raise RenderError(f"o ffmpeg falhou a fazer a capa de {src.name}: {detail[0]}")
