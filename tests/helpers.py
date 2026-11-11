"""Auxiliares partilhados pelos testes."""

from datetime import UTC, datetime, timedelta

from clipper.config import SelectionConfig
from clipper.models import Clip, Moment

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
T0 = NOW - timedelta(hours=3)
HOUR = timedelta(hours=1)

_UNSET = object()


def clip(
    id="Abc",
    *,
    game="123",
    duration=30.0,
    views=100,
    created=T0,
    video=_UNSET,
    offset=0,
    broadcaster="1",
    login="shroud",
    name="Shroud",
    title="wow",
) -> Clip:
    return Clip(
        id=id,
        url="https://clips.twitch.tv/" + id,
        broadcaster_id=broadcaster,
        broadcaster_login=login,
        broadcaster_name=name,
        title=title,
        game_id=game,
        view_count=views,
        created_at=created,
        duration=duration,
        video_id="v-" + id if video is _UNSET else video,
        vod_offset=offset,
    )


def m(*, video="v1", offset=0, created=T0, broadcaster="1") -> Moment:
    return Moment(broadcaster, video, offset, created)


def args(**over) -> dict:
    base = dict(
        game_id="123",
        cfg=SelectionConfig(),
        done_ids=set(),
        seen_moments=[],
        delivered_today=0,
        now=NOW,
    )
    base.update(over)
    return base


def ids(clips) -> list[str]:
    return [c.id for c in clips]
