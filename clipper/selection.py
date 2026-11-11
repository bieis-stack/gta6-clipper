"""Filtrar, remover repetidos e ordenar clips candidatos. Só funções puras."""

from __future__ import annotations

from datetime import datetime

from clipper.config import SelectionConfig
from clipper.models import Clip, Moment

SAME_VOD_SECONDS = 60
SAME_CREATION_SECONDS = 120
MIN_AGE_MINUTES = 10


def same_moment(a: Moment, b: Moment) -> bool:
    """Dois clips mostram o mesmo instante da stream?"""
    both_have_vod = None not in (a.video_id, a.vod_offset, b.video_id, b.vod_offset)
    if both_have_vod:
        return a.video_id == b.video_id and abs(a.vod_offset - b.vod_offset) < SAME_VOD_SECONDS
    apart = abs((a.created_at - b.created_at).total_seconds())
    return a.broadcaster_id == b.broadcaster_id and apart < SAME_CREATION_SECONDS


def score(clip: Clip, now: datetime) -> float:
    """Visualizações por minuto de vida, com um mínimo de idade para não
    premiar por acaso um clip acabado de criar."""
    age_minutes = (now - clip.created_at).total_seconds() / 60
    return clip.view_count / max(age_minutes, MIN_AGE_MINUTES)


def eligible(
    clips: list[Clip], *, game_id: str, cfg: SelectionConfig, done_ids: set[str]
) -> list[Clip]:
    """Clips que cumprem os filtros, antes de remover repetidos e aplicar limites."""
    return [
        clip
        for clip in clips
        if clip.game_id == game_id
        and cfg.min_duration <= clip.duration <= cfg.max_duration
        and clip.view_count >= cfg.min_views
        and clip.id not in done_ids
    ]


def select(
    clips: list[Clip],
    *,
    game_id: str,
    cfg: SelectionConfig,
    done_ids: set[str],
    seen_moments: list[Moment],
    delivered_today: int,
    now: datetime,
) -> list[Clip]:
    limit = min(cfg.max_per_run, cfg.max_per_day - delivered_today)
    candidates = eligible(clips, game_id=game_id, cfg=cfg, done_ids=done_ids)
    candidates.sort(key=lambda clip: score(clip, now), reverse=True)

    chosen: list[Clip] = []
    taken = list(seen_moments)
    for clip in candidates:
        if len(chosen) >= limit:
            break
        if any(same_moment(clip.moment, moment) for moment in taken):
            continue
        chosen.append(clip)
        taken.append(clip.moment)
    return chosen
