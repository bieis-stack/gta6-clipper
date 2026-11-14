import logging
import shutil
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from clipper import pipeline
from clipper.captions import Word
from clipper.config import Config, HookConfig, SelectionConfig
from clipper.layout import RenderError
from clipper.media import probe
from clipper.models import Rect, RenderedClip, Streamer
from clipper.pipeline import GameNotFound, RunSummary, process_clip, run
from clipper.publishers.base import PublishError
from clipper.state import State
from clipper.twitch import TwitchAuthError, TwitchError, User
from clipper.writer import Texts, fallback_hook
from tests.helpers import HOUR, NOW, T0, clip

ASSETS = Path(__file__).parent.parent / "assets"
SHROUD = Streamer("shroud")
OTHER = Streamer("other")


def config(*streamers, **selection):
    return Config(
        game_name="Grand Theft Auto VI",
        streamers=streamers or (SHROUD,),
        selection=SelectionConfig(**selection),
        hashtags=("#GTA6", "#shorts"),
    )


class FakeTwitch:
    def __init__(self, clips_by_login, *, game_id="123"):
        self.clips_by_login = clips_by_login
        self.game_id = game_id
        self.unknown = set()
        self.failing = set()
        self.auth_error = False
        self.clip_calls = []

    def get_game_id(self, name):
        return self.game_id

    def get_users(self, logins):
        if self.auth_error:
            raise TwitchAuthError("bad credentials")
        return {
            login: User("id-" + login, login, login.title())
            for login in logins
            if login not in self.unknown
        }

    def get_clips(self, user, started_at, ended_at):
        self.clip_calls.append((user.login, started_at, ended_at))
        if user.login in self.failing:
            raise TwitchError("boom")
        return list(self.clips_by_login.get(user.login, []))


class FakePublisher:
    def __init__(self):
        self.published = []
        self.fail = False

    def publish(self, item):
        if self.fail:
            raise PublishError("telegram down")
        self.published.append(item.clip.id)


def fake_process(clip, streamer):
    return RenderedClip(clip, Path("x.mp4"), clip.title, "desc")


def three_clips():
    return [
        clip("slow", views=100, created=T0),
        clip("fast", views=900, created=T0 + HOUR),
        clip("mid", views=300, created=T0 + 2 * HOUR),
    ]


def test_delivers_best_clips_and_records_them():
    state, publisher = State(), FakePublisher()
    summary = run(
        config(), state, FakeTwitch({"shroud": three_clips()}), publisher, now=NOW, process=fake_process
    )
    assert publisher.published == ["fast", "mid"]
    assert summary == RunSummary(candidates=3, delivered=2, failed=0)
    assert state.done_ids() == {"fast", "mid"}
    assert state.delivered_today(NOW) == 2


def test_requests_clips_for_lookback_window():
    twitch = FakeTwitch({})
    run(config(), State(), twitch, FakePublisher(), now=NOW, process=fake_process)
    assert twitch.clip_calls == [("shroud", NOW - timedelta(hours=6), NOW)]


def test_process_receives_the_streamer_of_each_clip():
    seen = []

    def process(c, streamer):
        seen.append((c.id, streamer))
        return fake_process(c, streamer)

    cam = Streamer("other", Rect(0, 0, 100, 100))
    twitch = FakeTwitch({"shroud": [clip("a")], "other": [clip("b", broadcaster="2", login="other")]})
    run(config(SHROUD, cam), State(), twitch, FakePublisher(), now=NOW, process=process)
    assert sorted(seen, key=lambda pair: pair[0]) == [("a", SHROUD), ("b", cam)]


def test_one_failing_clip_does_not_stop_the_next():
    def process(c, streamer):
        if c.id == "fast":
            raise RuntimeError("download failed")
        return fake_process(c, streamer)

    state, publisher = State(), FakePublisher()
    summary = run(
        config(), state, FakeTwitch({"shroud": three_clips()}), publisher, now=NOW, process=process
    )
    assert publisher.published == ["mid"]
    assert summary == RunSummary(candidates=3, delivered=1, failed=1)
    assert "fast" not in state.done_ids()


def test_publish_failure_is_recorded_and_not_counted_today():
    state, publisher = State(), FakePublisher()
    publisher.fail = True
    summary = run(
        config(), state, FakeTwitch({"shroud": [clip("a")]}), publisher, now=NOW, process=fake_process
    )
    assert summary == RunSummary(candidates=1, delivered=0, failed=1)
    assert state.delivered_today(NOW) == 0


def test_clip_is_dropped_after_three_failures():
    def process(c, streamer):
        raise RuntimeError("always")

    state, twitch = State(), FakeTwitch({"shroud": [clip("a")]})
    for _ in range(3):
        assert run(config(), state, twitch, FakePublisher(), now=NOW, process=process).failed == 1
    fourth = run(config(), state, twitch, FakePublisher(), now=NOW, process=process)
    assert fourth == RunSummary(candidates=0, delivered=0, failed=0)


def test_unknown_streamer_is_skipped_with_warning(caplog):
    twitch = FakeTwitch({"shroud": [clip("a")]})
    twitch.unknown = {"ghost"}
    publisher = FakePublisher()
    with caplog.at_level(logging.WARNING):
        run(config(Streamer("ghost"), SHROUD), State(), twitch, publisher, now=NOW, process=fake_process)
    assert publisher.published == ["a"]
    assert "ghost" in caplog.text


def test_twitch_error_for_one_streamer_does_not_stop_the_others(caplog):
    twitch = FakeTwitch({"other": [clip("b", broadcaster="2", login="other")]})
    twitch.failing = {"shroud"}
    publisher = FakePublisher()
    with caplog.at_level(logging.WARNING):
        run(config(SHROUD, OTHER), State(), twitch, publisher, now=NOW, process=fake_process)
    assert publisher.published == ["b"]
    assert "shroud" in caplog.text


def test_auth_error_aborts():
    twitch = FakeTwitch({})
    twitch.auth_error = True
    with pytest.raises(TwitchAuthError):
        run(config(), State(), twitch, FakePublisher(), now=NOW, process=fake_process)


def test_game_not_found_aborts():
    with pytest.raises(GameNotFound, match="Grand Theft Auto VI"):
        run(config(), State(), FakeTwitch({}, game_id=None), FakePublisher(), now=NOW, process=fake_process)


def test_no_streamers_or_no_candidates_is_a_clean_noop():
    publisher = FakePublisher()
    empty = replace(config(), streamers=())
    assert run(empty, State(), FakeTwitch({}), publisher, now=NOW, process=fake_process) == RunSummary(0, 0, 0)
    assert run(config(), State(), FakeTwitch({}), publisher, now=NOW, process=fake_process) == RunSummary(0, 0, 0)
    assert publisher.published == []


def test_state_is_pruned():
    state = State()
    state.record_delivered(clip("old"), NOW - timedelta(days=15))
    run(config(), state, FakeTwitch({}), FakePublisher(), now=NOW, process=fake_process)
    assert state.done_ids() == set()


def test_already_delivered_moments_are_not_sent_again():
    state = State()
    state.record_delivered(clip("first", video="v1", offset=100), NOW - HOUR)
    twitch = FakeTwitch({"shroud": [clip("again", video="v1", offset=110)]})
    publisher = FakePublisher()
    run(config(), state, twitch, publisher, now=NOW, process=fake_process)
    assert publisher.published == []


# --- process_clip: cadeia real de edição, com rede e modelos substituídos ---


@pytest.fixture
def offline(monkeypatch, make_video):
    source = make_video(seconds=2)

    def fake_download(url, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)
        return Path(shutil.copy(source, dest_dir / "Abc.mp4"))

    monkeypatch.setattr(pipeline, "download_clip", fake_download)
    monkeypatch.setattr(pipeline, "transcribe", lambda video: [Word(0.2, 0.6, "hello")])
    monkeypatch.setattr(pipeline, "detect_facecam", lambda video, model: None)


def test_process_clip_produces_a_publishable_video(offline, tmp_path):
    item = process_clip(clip("Abc", title="what a {play}"), SHROUD, config(), tmp_path / "work", ASSETS)
    info = probe(item.video_path)
    assert (info.width, info.height) == (1080, 1920)
    assert item.title == "what a {play} | Shroud #GTA6"
    assert item.description.endswith("#GTA6 #shorts")
    assert item.clip.id == "Abc"


def test_process_clip_uses_the_manual_facecam_zone(offline, tmp_path, monkeypatch):
    used = {}
    real_render = pipeline.render

    def spy(src, dst, **kwargs):
        used.update(kwargs)
        return real_render(src, dst, **kwargs)

    monkeypatch.setattr(pipeline, "render", spy)
    monkeypatch.setattr(pipeline, "detect_facecam", lambda video, model: pytest.fail("não devia detetar"))
    streamer = Streamer("shroud", Rect(0, 600, 480, 360))
    process_clip(clip("Abc"), streamer, config(), tmp_path / "work", ASSETS)
    assert used["facecam"] == Rect(0, 600, 480, 360)


def test_process_clip_falls_back_to_detection_when_manual_zone_is_outside(offline, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "detect_facecam", lambda video, model: calls.append(video))
    streamer = Streamer("shroud", Rect(5000, 5000, 100, 100))
    process_clip(clip("Abc"), streamer, config(), tmp_path / "work", ASSETS)
    assert len(calls) == 1


def test_process_clip_survives_a_transcription_failure(offline, tmp_path, monkeypatch, caplog):
    def broken(video):
        raise RuntimeError("whisper exploded")

    monkeypatch.setattr(pipeline, "transcribe", broken)
    with caplog.at_level(logging.WARNING):
        item = process_clip(clip("Abc"), SHROUD, config(), tmp_path / "work", ASSETS)
    assert item.video_path.exists()
    assert "legendas" in caplog.text


def test_process_clip_without_hashtags_has_no_tag_in_title(offline, tmp_path):
    cfg = replace(config(), hashtags=())
    item = process_clip(clip("Abc", title="wow"), SHROUD, cfg, tmp_path / "work", ASSETS)
    assert item.title == "wow | Shroud"


def test_checkpoint_runs_after_each_clip_so_an_interrupted_run_loses_nothing():
    state, saved = State(), []

    def checkpoint():
        saved.append(set(state.done_ids()))

    run(
        config(),
        state,
        FakeTwitch({"shroud": three_clips()}),
        FakePublisher(),
        now=NOW,
        process=fake_process,
        checkpoint=checkpoint,
    )
    assert {"fast"} in saved
    assert saved[-1] == {"fast", "mid"}


class Killed(BaseException):
    """Simula o GitHub a matar a execução a meio de um clip."""


def test_a_run_killed_mid_clip_still_counts_as_an_attempt():
    state, twitch, checkpoints = State(), FakeTwitch({"shroud": [clip("a")]}), []

    def process(c, streamer):
        raise Killed()

    for _ in range(3):
        with pytest.raises(Killed):
            run(config(), state, twitch, FakePublisher(), now=NOW, process=process,
                checkpoint=lambda: checkpoints.append(1))
    assert len(checkpoints) == 3  # o estado foi gravado antes de cada tentativa
    after = run(config(), state, twitch, FakePublisher(), now=NOW, process=fake_process)
    assert after == RunSummary(candidates=0, delivered=0, failed=0)


def test_stops_starting_clips_when_out_of_time():
    state, publisher = State(), FakePublisher()
    answers = iter([False, True])
    summary = run(
        config(), state, FakeTwitch({"shroud": three_clips()}), publisher, now=NOW,
        process=fake_process, out_of_time=lambda: next(answers),
    )
    assert publisher.published == ["fast"]
    assert summary == RunSummary(candidates=3, delivered=1, failed=0)
    later = run(config(), state, FakeTwitch({"shroud": three_clips()}), publisher, now=NOW, process=fake_process)
    assert "mid" in publisher.published and later.failed == 0


# --- fonte sem chaves: o jogo só se conhece consultando clip a clip ---


class FakePublicTwitch(FakeTwitch):
    def __init__(self, clips_by_login, games):
        super().__init__(clips_by_login)
        self.games = games
        self.lookups = []

    def resolve_game(self, c):
        self.lookups.append(c.id)
        game = self.games.get(c.id)
        return None if game is None else replace(c, game_id=game)


def test_unknown_games_are_resolved_and_other_games_remembered_as_skipped():
    clips = [clip("gta", game=None, views=900), clip("irl", game=None, views=800)]
    twitch = FakePublicTwitch({"shroud": clips}, {"gta": "123", "irl": "999"})
    state, publisher = State(), FakePublisher()
    summary = run(config(), state, twitch, publisher, now=NOW, process=fake_process)
    assert publisher.published == ["gta"]
    assert summary.delivered == 1
    assert twitch.lookups == ["gta", "irl"]
    # na execução seguinte o clip de outro jogo já não gasta uma consulta
    twitch.lookups.clear()
    run(config(), state, twitch, publisher, now=NOW, process=fake_process)
    assert twitch.lookups == []


def test_rejected_clips_are_logged_with_their_game(caplog):
    twitch = FakePublicTwitch({"shroud": [clip("irl", game=None)]}, {"irl": "irl"})
    with caplog.at_level(logging.INFO):
        run(config(), State(), twitch, FakePublisher(), now=NOW, process=fake_process)
    assert "irl" in caplog.text and "outro jogo" in caplog.text


def test_clips_skipped_for_another_game_count_again_when_the_game_changes():
    state = State()
    state.record_skipped(clip("gta5", game="999"), NOW)
    twitch = FakeTwitch({"shroud": [clip("gta5", game="999")]}, game_id="999")
    publisher = FakePublisher()
    run(config(), state, twitch, publisher, now=NOW, process=fake_process)
    assert publisher.published == ["gta5"]


def test_without_a_publisher_clips_are_only_counted_never_processed():
    clips = [clip("gta", game=None, views=900), clip("irl", game=None, views=800)]
    twitch = FakePublicTwitch({"shroud": clips}, {"gta": "123", "irl": "999"})
    state = State()

    def process(c, streamer):
        raise AssertionError("não devia editar sem destino")

    summary = run(config(), state, twitch, None, now=NOW, process=process)
    assert summary == RunSummary(candidates=2, delivered=0, failed=0, waiting=1)
    assert state.done_ids("123") == {"irl"}  # o de outro jogo fica registado; o bom fica à espera


# --- gancho: flash-forward, texto, capa ---


@pytest.fixture
def long_offline(monkeypatch, make_video):
    source = make_video(seconds=12)

    def fake_download(url, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)
        return Path(shutil.copy(source, dest_dir / "Abc.mp4"))

    monkeypatch.setattr(pipeline, "download_clip", fake_download)
    monkeypatch.setattr(pipeline, "transcribe", lambda video: [Word(0.2, 0.6, "hello")])
    monkeypatch.setattr(pipeline, "detect_facecam", lambda video, model: None)
    monkeypatch.setattr(pipeline, "choose_flash", lambda audio, rate, seconds: 6.0)


def test_process_clip_opens_with_the_peak_and_the_written_hook(long_offline, tmp_path):
    asked = {}

    def write(transcript, clip_):
        asked.update(transcript=transcript, clip=clip_.id)
        return Texts(hook="HE STOLE A JET", title="He stole a jet 😭", source="gemini")

    item = process_clip(clip("Abc"), SHROUD, config(), tmp_path / "work", ASSETS, write=write)
    assert asked == {"transcript": "hello", "clip": "Abc"}
    assert probe(item.video_path).duration == pytest.approx(13.5, abs=0.2)
    assert item.title == "He stole a jet 😭 | Shroud #GTA6"
    assert item.description.startswith("He stole a jet 😳")
    assert item.cover_path is not None and item.cover_path.read_bytes()[:2] == b"\xff\xd8"
    ass = (tmp_path / "work" / "Abc.ass").read_text(encoding="utf-8")
    assert "HE STOLE A JET" in ass


def test_process_clip_without_writer_uses_the_fixed_hook(long_offline, tmp_path):
    item = process_clip(clip("Abc", title="wow"), SHROUD, config(), tmp_path / "work", ASSETS)
    ass = (tmp_path / "work" / "Abc.ass").read_text(encoding="utf-8")
    assert fallback_hook("Abc") in ass
    assert item.title == "wow | Shroud #GTA6"


def test_process_clip_with_hook_disabled_keeps_the_old_video(long_offline, tmp_path):
    cfg = replace(config(), hook=HookConfig(enabled=False))
    item = process_clip(clip("Abc", title="wow"), SHROUD, cfg, tmp_path / "work", ASSETS)
    assert probe(item.video_path).duration == pytest.approx(12.0, abs=0.2)
    assert "wow" in (tmp_path / "work" / "Abc.ass").read_text(encoding="utf-8")


def test_process_clip_survives_a_broken_writer_and_cover(long_offline, tmp_path, monkeypatch, caplog):
    def broken_write(transcript, clip_):
        raise RuntimeError("boom")

    def broken_cover(*args, **kwargs):
        raise RenderError("no cover")

    monkeypatch.setattr(pipeline, "render_cover", broken_cover)
    with caplog.at_level(logging.WARNING):
        item = process_clip(clip("Abc"), SHROUD, config(), tmp_path / "work", ASSETS, write=broken_write)
    assert item.video_path.exists() and item.cover_path is None
    assert fallback_hook("Abc") in (tmp_path / "work" / "Abc.ass").read_text(encoding="utf-8")
