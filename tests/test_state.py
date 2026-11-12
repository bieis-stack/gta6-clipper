import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from clipper.state import State, StateError
from tests.helpers import NOW, clip


def test_missing_file_is_empty(tmp_path):
    assert State.load(tmp_path / "s.json").done_ids() == set()


@pytest.mark.parametrize("content", ["", "{not json", '{"version": 2, "clips": {}}', "[]"])
def test_corrupt_file_raises(tmp_path, content):
    p = tmp_path / "s.json"
    p.write_text(content)
    with pytest.raises(StateError):
        State.load(p)


def test_roundtrip(tmp_path):
    s = State.load(tmp_path / "s.json")
    s.record_delivered(clip("a"), NOW)
    s.save(tmp_path / "sub" / "s.json")
    again = State.load(tmp_path / "sub" / "s.json")
    assert again.done_ids() == {"a"}
    assert again.delivered_moments() == [clip("a").moment]


def test_roundtrip_keeps_clip_without_vod(tmp_path):
    s = State()
    s.record_delivered(clip("a", video=None, offset=None), NOW)
    s.save(tmp_path / "s.json")
    assert State.load(tmp_path / "s.json").delivered_moments() == [
        clip("a", video=None, offset=None).moment
    ]


def test_failure_becomes_final_on_third_attempt():
    s = State()
    c = clip("a")
    s.record_failure(c, NOW)
    s.record_failure(c, NOW)
    assert "a" not in s.done_ids()
    s.record_failure(c, NOW)
    assert "a" in s.done_ids()
    assert s.delivered_moments() == []


def test_failures_survive_a_roundtrip(tmp_path):
    s = State()
    s.record_failure(clip("a"), NOW)
    s.record_failure(clip("a"), NOW)
    s.save(tmp_path / "s.json")
    again = State.load(tmp_path / "s.json")
    again.record_failure(clip("a"), NOW)
    assert "a" in again.done_ids()


def test_delivered_after_retry_counts_as_delivered():
    s = State()
    s.record_failure(clip("a"), NOW)
    s.record_delivered(clip("a"), NOW)
    assert s.delivered_today(NOW) == 1


def test_delivered_today_uses_utc_date():
    s = State()
    s.record_delivered(clip("a"), datetime(2026, 11, 19, 23, 59, tzinfo=UTC))
    s.record_delivered(clip("b"), datetime(2026, 11, 20, 0, 1, tzinfo=UTC))
    assert s.delivered_today(datetime(2026, 11, 20, 12, 0, tzinfo=UTC)) == 1


def test_failures_do_not_count_as_delivered_today():
    s = State()
    for _ in range(3):
        s.record_failure(clip("a"), NOW)
    assert s.delivered_today(NOW) == 0


def test_prune_drops_entries_older_than_14_days():
    s = State()
    s.record_delivered(clip("old"), NOW - timedelta(days=15))
    s.record_delivered(clip("new"), NOW)
    s.prune(NOW)
    assert s.done_ids() == {"new"}


def test_skipped_clips_are_done_but_neither_delivered_nor_moments(tmp_path):
    s = State()
    s.record_skipped(clip("other-game"), NOW)
    s.save(tmp_path / "s.json")
    again = State.load(tmp_path / "s.json")
    assert again.done_ids() == {"other-game"}
    assert again.delivered_today(NOW) == 0
    assert again.delivered_moments() == []


def test_a_clip_skipped_for_one_game_is_a_candidate_when_looking_for_its_own_game(tmp_path):
    s = State()
    s.record_skipped(replace(clip("mc"), game_id="minecraft"), NOW)
    s.save(tmp_path / "s.json")
    again = State.load(tmp_path / "s.json")
    assert "mc" in again.done_ids("grand theft auto vi")
    assert "mc" not in again.done_ids("minecraft")


def test_skipped_entry_without_a_known_game_does_not_hide_the_clip(tmp_path):
    """Entradas gravadas antes de o jogo ser guardado não devem esconder clips."""
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"version": 1, "clips": {"old": {
        "broadcaster_id": "1", "video_id": None, "vod_offset": None,
        "created_at": NOW.isoformat(), "status": "skipped", "attempts": 0,
        "updated_at": NOW.isoformat(),
    }}}))
    assert "old" not in State.load(p).done_ids("minecraft")
