from clipper.metadata import build_description, build_title
from tests.helpers import clip

CLIP = clip("Abc")


def test_title_format():
    assert build_title("He did WHAT", "Shroud", "#GTA6") == "He did WHAT | Shroud #GTA6"


def test_title_truncates_clip_part_and_keeps_suffix():
    t = build_title("x" * 200, "Shroud", "#GTA6")
    assert len(t) == 100 and t.endswith("… | Shroud #GTA6")


def test_title_at_exact_limit_is_not_truncated():
    suffix = " | Shroud #GTA6"
    t = build_title("x" * (100 - len(suffix)), "Shroud", "#GTA6")
    assert len(t) == 100 and "…" not in t


def test_title_collapses_whitespace_and_handles_empty():
    assert build_title("  a \n b  ", "S", "#T") == "a b | S #T"
    assert build_title("   ", "S", "#T") == "S #T"


def test_title_without_tag():
    assert build_title("a", "S", "") == "a | S"


def test_title_never_exceeds_limit_even_with_huge_streamer_name():
    assert len(build_title("a", "N" * 300, "#T")) <= 100


def test_description():
    assert build_description(CLIP, ("#GTA6", "#shorts")) == (
        "🎥 Shroud → https://twitch.tv/shroud\n"
        "Clip: https://clips.twitch.tv/Abc\n"
        "\n"
        "#GTA6 #shorts"
    )


def test_description_without_hashtags_has_no_trailing_blank_lines():
    assert build_description(CLIP, ()) == (
        "🎥 Shroud → https://twitch.tv/shroud\nClip: https://clips.twitch.tv/Abc"
    )


def test_description_opens_with_the_hook_and_tags_the_streamer():
    assert build_description(CLIP, ("#GTA6", "#shorts"), hook="HE STOLE A JET") == (
        "He stole a jet 😳\n"
        "\n"
        "🎥 Shroud → https://twitch.tv/shroud\n"
        "Clip: https://clips.twitch.tv/Abc\n"
        "\n"
        "#shroud #GTA6 #shorts"
    )
