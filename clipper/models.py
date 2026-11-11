"""Tipos partilhados por todas as unidades."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Streamer:
    twitch: str
    facecam: Rect | None = None


@dataclass(frozen=True)
class Moment:
    """O instante de uma stream a que um clip se refere, para detetar repetidos."""

    broadcaster_id: str
    video_id: str | None
    vod_offset: int | None
    created_at: datetime


@dataclass(frozen=True)
class Clip:
    id: str
    url: str
    broadcaster_id: str
    broadcaster_login: str
    broadcaster_name: str
    title: str
    game_id: str
    view_count: int
    created_at: datetime
    duration: float
    video_id: str | None
    vod_offset: int | None

    @property
    def moment(self) -> Moment:
        return Moment(self.broadcaster_id, self.video_id, self.vod_offset, self.created_at)


@dataclass(frozen=True)
class RenderedClip:
    clip: Clip
    video_path: Path
    title: str
    description: str
