import pytest

from clipper.config import ConfigError, SelectionConfig, load_config
from clipper.models import Rect, Streamer

FULL = """
game_name: "Grand Theft Auto VI"
streamers:
  - twitch: "  Shroud "
    facecam: {x: 0, y: 720, w: 480, h: 360}
  - twitch: other
selection: {max_per_day: 3}
metadata: {hashtags: ["#A", "#B"]}
"""


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_full(tmp_path):
    cfg = load_config(write(tmp_path, FULL))
    assert cfg.game_name == "Grand Theft Auto VI"
    assert cfg.streamers == (Streamer("shroud", Rect(0, 720, 480, 360)), Streamer("other"))
    assert cfg.selection == SelectionConfig(max_per_day=3)
    assert cfg.hashtags == ("#A", "#B")


def test_defaults(tmp_path):
    cfg = load_config(write(tmp_path, 'game_name: "X"'))
    assert cfg.streamers == ()
    assert cfg.selection == SelectionConfig(6, 30, 15, 60, 2, 5)
    assert cfg.hashtags == ("#GTA6", "#GTAVI", "#shorts")


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("streamers: []", "game_name"),
        ('game_name: "X"\nselection: {min_duration: 70}', "min_duration"),
        ('game_name: "X"\nstreamers: [{twitch: a, facecam: {x: 0, y: 0, w: 0, h: 10}}]', "facecam"),
        ('game_name: "X"\nstreamrs: []', "streamrs"),
        ("- not a mapping", "config"),
    ],
)
def test_invalid(tmp_path, text, fragment):
    with pytest.raises(ConfigError, match=fragment):
        load_config(write(tmp_path, text))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


@pytest.mark.parametrize(
    "written",
    ["https://www.twitch.tv/Shroud", "twitch.tv/shroud/", "@Shroud", "http://twitch.tv/shroud?tab=clips"],
)
def test_login_accepts_pasted_channel_links_and_handles(tmp_path, written):
    cfg = load_config(write(tmp_path, f'game_name: "X"\nstreamers: [{{twitch: "{written}"}}]'))
    assert cfg.streamers == (Streamer("shroud"),)


@pytest.mark.parametrize("written", ["Nome Com Espaços", "çãõ", "a" * 26, "https://youtube.com/@x"])
def test_login_that_cannot_be_a_twitch_channel_is_rejected_by_name(tmp_path, written):
    with pytest.raises(ConfigError, match="twitch"):
        load_config(write(tmp_path, f'game_name: "X"\nstreamers: [{{twitch: "{written}"}}]'))


def test_hook_defaults(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("game_name: X\n", encoding="utf-8")
    hook = load_config(path).hook
    assert hook.enabled is True and hook.seconds == 1.5 and hook.model == "gemini-flash-latest"


def test_hook_section(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text("game_name: X\nhook: {enabled: false, seconds: 2, model: m}\n", encoding="utf-8")
    hook = load_config(path).hook
    assert (hook.enabled, hook.seconds, hook.model) == (False, 2, "m")


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("hook: {colour: red}", "chave desconhecida"),
        ("hook: {seconds: -1}", "seconds"),
        ("hook: {enabled: 1}", "enabled"),
        ("hook: {model: ''}", "model"),
    ],
)
def test_hook_invalid(tmp_path, text, fragment):
    path = tmp_path / "c.yaml"
    path.write_text(f"game_name: X\n{text}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=fragment):
        load_config(path)
