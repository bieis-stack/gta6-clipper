"""Download do vídeo de um clip com o yt-dlp."""

from __future__ import annotations

from pathlib import Path

import yt_dlp


class DownloadError(Exception):
    pass


def download_clip(url: str, dest_dir: Path) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "socket_timeout": 30,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except yt_dlp.utils.DownloadError as error:
        raise DownloadError(f"falha ao descarregar {url}: {error}") from None
    if not path.exists():
        raise DownloadError(f"o download de {url} não produziu nenhum ficheiro")
    return path
