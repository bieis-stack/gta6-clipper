"""Filtrar, remover repetidos e ordenar clips candidatos. Só funções puras."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from clipper.config import SelectionConfig
from clipper.models import Clip, Moment

SAME_VOD_SECONDS = 60
SAME_CREATION_SECONDS = 120
MIN_AGE_MINUTES = 10
MAX_LOOKUPS = 12


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
        if (clip.game_id == game_id or clip.game_id is None)
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
    resolve: Callable[[Clip], Clip | None] | None = None,
    on_reject: Callable[[Clip], None] | None = None,
    max_lookups: int = MAX_LOOKUPS,
) -> list[Clip]:
    """Escolhe os melhores clips.

    Quando o jogo de um clip é desconhecido, `resolve` descobre-o (um pedido
    à Twitch por clip), só para os candidatos mais bem colocados e no máximo
    `max_lookups` vezes. `on_reject` recebe os que afinal são de outro jogo.
    """
    limit = min(cfg.max_per_run, cfg.max_per_day - delivered_today)
    candidates = eligible(clips, game_id=game_id, cfg=cfg, done_ids=done_ids)
    candidates.sort(key=lambda clip: score(clip, now), reverse=True)

    chosen: list[Clip] = []
    lookups = 0
    taken = list(seen_moments)
    for clip in candidates:
        if len(chosen) >= limit:
            break
        if any(same_moment(clip.moment, moment) for moment in taken):
            continue
        if clip.game_id is None:
            if resolve is None or lookups >= max_lookups:
                continue
            lookups += 1
            clip = resolve(clip)
            if clip is None:
                continue
            if clip.game_id != game_id:
                if on_reject is not None:
                    on_reject(clip)
                continue
        chosen.append(clip)
        taken.append(clip.moment)
    return chosen
