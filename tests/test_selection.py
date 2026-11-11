from datetime import timedelta

from clipper.config import SelectionConfig
from clipper.selection import same_moment, score, select
from tests.helpers import HOUR, NOW, T0, args, clip, ids, m


def test_same_moment_same_vod_within_60s():
    assert same_moment(m(video="v1", offset=100), m(video="v1", offset=159))
    assert not same_moment(m(video="v1", offset=100), m(video="v1", offset=160))
    assert not same_moment(m(video="v1", offset=100), m(video="v2", offset=100))


def test_same_moment_without_vod_uses_created_at_within_120s():
    a = m(video=None, offset=None, created=NOW)
    assert same_moment(a, m(video=None, offset=None, created=NOW + timedelta(seconds=119)))
    assert not same_moment(a, m(video=None, offset=None, created=NOW + timedelta(seconds=120)))
    assert same_moment(a, m(video="v1", offset=5, created=NOW + timedelta(seconds=10)))
    assert not same_moment(a, m(video=None, offset=None, created=NOW, broadcaster="other"))


def test_score_is_views_per_minute_with_10_minute_floor():
    assert score(clip(views=600, created=NOW - timedelta(minutes=60)), NOW) == 10.0
    assert score(clip(views=600, created=NOW - timedelta(minutes=1)), NOW) == 60.0


def test_select_filters():
    clips = [
        clip("ok"),
        clip("wrong_game", game="999"),
        clip("short", duration=14.9),
        clip("long", duration=60.1),
        clip("few", views=29),
        clip("done"),
    ]
    assert ids(select(clips, **args(done_ids={"done"}))) == ["ok"]


def test_select_bounds_are_inclusive():
    clips = [
        clip("a", duration=15, views=30, created=T0),
        clip("b", duration=60, created=T0 + HOUR),
    ]
    assert len(select(clips, **args(cfg=SelectionConfig(max_per_run=5)))) == 2


def test_select_orders_by_score_and_caps_per_run():
    clips = [
        clip("slow", views=100, created=T0),
        clip("fast", views=900, created=T0 + HOUR),
        clip("mid", views=300, created=T0 + 2 * HOUR),
    ]
    assert ids(select(clips, **args())) == ["fast", "mid"]


def test_select_respects_daily_cap():
    clips = [clip("fast", views=900, created=T0 + HOUR), clip("slow", views=100, created=T0)]
    assert ids(select(clips, **args(delivered_today=4))) == ["fast"]
    assert select(clips, **args(delivered_today=5)) == []


def test_select_skips_duplicates_of_seen_and_of_chosen():
    best = clip("best", views=900, video="v1", offset=100)
    dupe = clip("dupe", views=800, video="v1", offset=120)
    seen = clip("seen", views=700, video="v2", offset=10)
    other = clip("other", views=50, video="v3", offset=0)
    out = select([best, dupe, seen, other], **args(seen_moments=[m(video="v2", offset=30)]))
    assert ids(out) == ["best", "other"]


def test_select_ignores_the_same_clip_listed_twice():
    assert ids(select([clip("a"), clip("a")], **args())) == ["a"]
