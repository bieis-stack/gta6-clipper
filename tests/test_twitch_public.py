import logging
from datetime import UTC, datetime, timedelta

import pytest
import yt_dlp

from clipper.models import Clip
from clipper.twitch import TwitchError, User
from clipper.twitch_public import PublicTwitch

END = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
START = END - timedelta(hours=6)
KAI = User("kaicenat", "kaicenat", "kaicenat")
SLUG = "DepressedArborealPotatoDatBoi-PZt5SSwQ1jq-vkr5"
CLIP_URL = f"https://www.twitch.tv/kaicenat/clip/{SLUG}"


def entry(slug=SLUG, *, hours_ago=1.0, **over):
    data = {
        "id": "3830116097",
        "title": "gta 6",
        "duration": 30.0,
        "view_count": 78,
        "timestamp": int((END - timedelta(hours=hours_ago)).timestamp()),
        "url": f"https://www.twitch.tv/kaicenat/clip/{slug}",
    }
    data.update(over)
    return data


class FakeYDL:
    results = {}
    calls = []

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        FakeYDL.calls.append((url, dict(self.options), download))
        result = FakeYDL.results[url]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def ydl(monkeypatch):
    FakeYDL.results, FakeYDL.calls = {}, []
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def listing(*entries, range_="24hr"):
    return {f"https://www.twitch.tv/kaicenat/clips?range={range_}": {"entries": list(entries)}}


def test_game_id_is_the_normalised_name():
    assert PublicTwitch().get_game_id("  Grand Theft Auto VI ") == "grand theft auto vi"


def test_users_are_taken_at_face_value():
    assert PublicTwitch().get_users(["KaiCenat", "xqc"]) == {
        "kaicenat": User("kaicenat", "kaicenat", "kaicenat"),
        "xqc": User("xqc", "xqc", "xqc"),
    }


def test_get_clips_parses_the_public_listing(ydl):
    ydl.results = listing(entry())
    assert PublicTwitch().get_clips(KAI, START, END) == [
        Clip(
            id=SLUG,
            url=CLIP_URL,
            broadcaster_id="kaicenat",
            broadcaster_login="kaicenat",
            broadcaster_name="kaicenat",
            title="gta 6",
            game_id=None,
            view_count=78,
            created_at=END - timedelta(hours=1),
            duration=30.0,
            video_id=None,
            vod_offset=None,
        )
    ]
    url, options, download = ydl.calls[0]
    assert options["extract_flat"] is True and options["playlistend"] == 50
    assert options["socket_timeout"] == 30 and download is False


def test_get_clips_keeps_only_the_requested_window(ydl):
    ydl.results = listing(entry("in"), entry("old", hours_ago=7), entry("future", hours_ago=-1))
    assert [c.id for c in PublicTwitch().get_clips(KAI, START, END)] == ["in"]


def test_get_clips_skips_entries_it_cannot_read(ydl):
    ydl.results = listing(entry("ok"), {"title": "sem url"}, entry("no-time", timestamp=None), None)
    assert [c.id for c in PublicTwitch().get_clips(KAI, START, END)] == ["ok"]


def test_get_clips_uses_the_weekly_listing_for_long_lookbacks(ydl):
    ydl.results = listing(entry(hours_ago=30), range_="7d")
    clips = PublicTwitch().get_clips(KAI, END - timedelta(hours=48), END)
    assert len(clips) == 1


@pytest.mark.parametrize(
    "error", [yt_dlp.utils.DownloadError("channel does not exist"), KeyError("entries")]
)
def test_listing_failure_is_a_twitch_error(ydl, error):
    ydl.results = {"https://www.twitch.tv/kaicenat/clips?range=24hr": error}
    with pytest.raises(TwitchError, match="kaicenat"):
        PublicTwitch().get_clips(KAI, START, END)


def test_empty_listing_is_no_clips(ydl):
    ydl.results = {"https://www.twitch.tv/kaicenat/clips?range=24hr": {"entries": []}}
    assert PublicTwitch().get_clips(KAI, START, END) == []


def a_clip(ydl):
    ydl.results = listing(entry())
    return PublicTwitch().get_clips(KAI, START, END)[0]


def test_resolve_game_reads_category_and_channel_name(ydl):
    clip = a_clip(ydl)
    ydl.results[CLIP_URL] = {"categories": ["Grand Theft Auto VI"], "channel": "KaiCenat"}
    resolved = PublicTwitch().resolve_game(clip)
    assert resolved.game_id == "grand theft auto vi"
    assert resolved.broadcaster_name == "KaiCenat"
    assert resolved.id == clip.id
    assert ydl.calls[-1][2] is False  # não descarrega o vídeo só para saber o jogo


def test_resolve_game_without_category_is_an_empty_game(ydl):
    clip = a_clip(ydl)
    ydl.results[CLIP_URL] = {"channel": "KaiCenat"}
    assert PublicTwitch().resolve_game(clip).game_id == ""


def test_resolve_game_failure_returns_none_and_warns(ydl, caplog):
    clip = a_clip(ydl)
    ydl.results[CLIP_URL] = yt_dlp.utils.DownloadError("gone")
    with caplog.at_level(logging.WARNING):
        assert PublicTwitch().resolve_game(clip) is None
    assert SLUG in caplog.text
