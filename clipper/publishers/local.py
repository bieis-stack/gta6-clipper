"""Grava os clips numa pasta local. Usado no modo de ensaio (--dry-run)."""

from __future__ import annotations

import shutil
from pathlib import Path

from clipper.models import RenderedClip
from clipper.publishers.base import PublishError


class LocalPublisher:
    def __init__(self, out_dir: Path) -> None:
        self._out_dir = Path(out_dir)

    def publish(self, item: RenderedClip) -> None:
        try:
            self._out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item.video_path, self._out_dir / f"{item.clip.id}.mp4")
            (self._out_dir / f"{item.clip.id}.txt").write_text(
                f"{item.title}\n\n{item.description}", encoding="utf-8"
            )
        except OSError as error:
            raise PublishError(f"não foi possível gravar o clip {item.clip.id}: {error}") from None
