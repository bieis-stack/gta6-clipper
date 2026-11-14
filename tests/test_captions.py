from types import SimpleNamespace

import numpy as np
import pytest

from clipper import captions
from clipper.captions import Cue, Word, build_ass, escape_ass, group_words, load_audio, transcribe


def words(text, step=0.2):
    return [Word(i * step, (i + 1) * step, w) for i, w in enumerate(text.split())]


def test_group_by_max_words():
    cues = group_words(words("a b c d e"))
    assert [c.text for c in cues] == ["A B C", "D E"]
    assert cues[0].start == 0.0 and cues[0].end == pytest.approx(0.6)


def test_group_keeps_each_word_with_its_time():
    cue = group_words(words("a b"))[0]
    assert [(w.start, w.text) for w in cue.words] == [(0.0, "A"), (0.2, "B")]


def test_build_ass_highlights_the_word_being_said():
    cue = group_words(words("hey you", step=0.5))[0]
    ass = build_ass([cue], title="", credit="", title_y=1, caption_y=700, credit_y=1, duration=5)
    lines = [line for line in ass.splitlines() if ",Caption," in line]
    assert len(lines) == 2
    assert lines[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50,Caption")
    assert "{\\c&H00FFFF&" in lines[0] and lines[0].index("HEY") < lines[0].index("{\\r}")
    assert lines[1].startswith("Dialogue: 0,0:00:00.50,0:00:01.00,Caption")
    assert lines[1].index("HEY") < lines[1].index("{\\c&H00FFFF&") < lines[1].index("YOU")


def test_build_ass_offset_delays_captions_but_not_the_title():
    ass = build_ass(
        [Cue(1.0, 1.8, "HELLO")],
        title="HOOK",
        credit="c",
        title_y=1,
        caption_y=2,
        credit_y=3,
        duration=21.5,
        offset=1.5,
    )
    assert "Dialogue: 0,0:00:00.00,0:00:03.00,Title" in ass
    assert "Dialogue: 0,0:00:02.50,0:00:03.30,Caption" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:21.50,Credit" in ass


def test_group_breaks_on_gap():
    w = [Word(0, 0.2, "a"), Word(0.9, 1.1, "b")]  # pausa de 0.7 s > 0.6
    assert [c.text for c in group_words(w)] == ["A", "B"]


def test_group_keeps_words_together_across_a_short_gap():
    w = [Word(0, 0.2, "a"), Word(0.7, 0.9, "b")]  # pausa de 0.5 s < 0.6
    assert [c.text for c in group_words(w)] == ["A B"]


def test_group_breaks_on_char_limit():
    cues = group_words(words("supercalifragilistic expialidocious"))
    assert len(cues) == 2


def test_group_strips_and_skips_empty_words():
    assert [c.text for c in group_words([Word(0, 0.2, " hi "), Word(0.2, 0.4, "  ")])] == ["HI"]


def test_group_empty():
    assert group_words([]) == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("a{b}c", "a(b)c"),
        ("a\\b", "a/b"),
        ("line1\nline2", "line1 line2"),
        ("it's 5:00 🔥", "it's 5:00 🔥"),
    ],
)
def test_escape_ass(raw, expected):
    assert escape_ass(raw) == expected


def test_build_ass_structure():
    ass = build_ass(
        [Cue(1.0, 1.8, "HELLO")],
        title="T{x}",
        credit="twitch.tv/shroud",
        title_y=1000,
        caption_y=768,
        credit_y=1880,
        duration=20.0,
    )
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Fontname" in ass and "Anton" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:03.00,Title,,0,0,0,,{\\pos(540,1000)}T(x)" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:20.00,Credit,,0,0,0,,{\\pos(540,1880)}twitch.tv/shroud" in ass
    assert "Dialogue: 0,0:00:01.00,0:00:01.80,Caption,,0,0,0,,{\\pos(540,768)}HELLO" in ass


def test_build_ass_title_never_outlasts_short_video():
    ass = build_ass([], title="T", credit="c", title_y=1, caption_y=1, credit_y=1, duration=2.0)
    assert "0:00:00.00,0:00:02.00,Title" in ass


def test_build_ass_without_title_or_cues_is_valid():
    ass = build_ass([], title="", credit="c", title_y=1, caption_y=1, credit_y=1, duration=5.0)
    assert ",Title," not in ass and ",Caption," not in ass


def test_build_ass_formats_times_past_one_minute():
    ass = build_ass(
        [Cue(61.5, 62.25, "X")], title="", credit="c", title_y=1, caption_y=7, credit_y=1, duration=70
    )
    assert "Dialogue: 0,0:01:01.50,0:01:02.25,Caption" in ass


def test_transcribe_video_without_audio_returns_no_words(make_video):
    assert transcribe(make_video(audio=False)) == []


def test_load_audio_is_16khz_mono_float32(make_video):
    audio = load_audio(make_video(seconds=2))
    assert audio.dtype == np.float32 and audio.ndim == 1
    assert len(audio) == pytest.approx(2 * 16000, rel=0.05)
    assert 0.01 < float(np.abs(audio).max()) <= 1.0


class FakeModel:
    def __init__(self):
        self.received = None

    def transcribe(self, audio, **options):
        self.received = (audio, options)
        word = SimpleNamespace(start=0.5, end=0.9, word=" hello")
        return iter([SimpleNamespace(words=[word]), SimpleNamespace(words=None)]), None


def test_transcribe_feeds_decoded_audio_to_the_model(make_video, monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(captions, "_model", fake)
    assert transcribe(make_video(seconds=2)) == [Word(0.5, 0.9, " hello")]
    audio, options = fake.received
    assert isinstance(audio, np.ndarray) and audio.dtype == np.float32
    assert options == {"word_timestamps": True, "vad_filter": True}
