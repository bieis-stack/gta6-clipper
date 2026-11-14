import numpy as np
import pytest

from clipper.hook import choose_flash, loudest_window

RATE = 16000


def tone(seconds, loud_from=None, loud_to=None, quiet=0.01, loud=0.8):
    """Áudio baixo com um troço alto entre loud_from e loud_to (em segundos)."""
    audio = np.full(int(seconds * RATE), quiet, dtype=np.float32)
    if loud_from is not None:
        audio[int(loud_from * RATE) : int(loud_to * RATE)] = loud
    return audio


def test_loudest_window_finds_the_loud_part():
    start = loudest_window(tone(20, 12.0, 13.5), RATE, window=1.5)
    assert start == pytest.approx(12.0, abs=0.1)


def test_loudest_window_never_runs_past_the_end():
    start = loudest_window(tone(10, 9.5, 10.0), RATE, window=1.5)
    assert start + 1.5 <= 10.0 + 1e-6


def test_loudest_window_of_audio_shorter_than_the_window_is_none():
    assert loudest_window(tone(1.0), RATE, window=1.5) is None


def test_loudest_window_of_empty_audio_is_none():
    assert loudest_window(np.zeros(0, dtype=np.float32), RATE, window=1.5) is None


def test_choose_flash_returns_the_peak():
    assert choose_flash(tone(30, 20.0, 21.5), RATE, seconds=1.5) == pytest.approx(20.0, abs=0.1)


def test_no_flash_for_short_clips():
    assert choose_flash(tone(7, 5.0, 6.0), RATE, seconds=1.5) is None


def test_no_flash_when_the_clip_already_opens_with_the_peak():
    assert choose_flash(tone(30, 0.5, 2.0), RATE, seconds=1.5) is None


def test_no_flash_for_silence():
    assert choose_flash(np.zeros(30 * RATE, dtype=np.float32), RATE, seconds=1.5) is None


def test_no_flash_when_disabled():
    assert choose_flash(tone(30, 20.0, 21.5), RATE, seconds=0) is None
