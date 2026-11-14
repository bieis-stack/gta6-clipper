import json

import pytest
import requests
import responses

from clipper import writer
from clipper.writer import FALLBACK_HOOKS, Texts, clean_hook, clean_title, fallback_hook, write_texts

GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"


def gemini_reply(payload) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def pollinations_reply(payload) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def call(**over) -> Texts:
    base = dict(
        transcript="no way he just did that bro",
        clip_title="lmao",
        streamer="xQc",
        game="Grand Theft Auto VI",
        clip_id="Clip1",
        api_key="KEY",
        model="gemini-flash-latest",
        session=requests.Session(),
    )
    base.update(over)
    return write_texts(**base)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("he jumped off the plane", "HE JUMPED OFF THE PLANE"),
        ('"WAIT FOR IT"', "WAIT FOR IT"),
        ("COPS LOST HIM 😂🔥", "COPS LOST HIM"),
        ("#GTA6 NO WAY", "NO WAY"),
        ("  WHY   WOULD  HE  ", "WHY WOULD HE"),
        ("HE DID WHAT?!", "HE DID WHAT?!"),
    ],
)
def test_clean_hook_accepts_and_tidies(raw, expected):
    assert clean_hook(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "WOW", "THIS IS A HOOK THAT HAS FAR TOO MANY WORDS IN IT", "A" * 45, None, 7, "😂 🔥"],
)
def test_clean_hook_rejects(raw):
    assert clean_hook(raw) is None


def test_clean_title_strips_hashtags_and_limits_length():
    assert clean_title("He robbed the bank solo #GTA6 #shorts") == "He robbed the bank solo"
    assert clean_title("x" * 120) is None
    assert clean_title("") is None
    assert clean_title(None) is None


def test_fallback_hook_is_stable_and_from_the_list():
    assert fallback_hook("abc") == fallback_hook("abc")
    assert fallback_hook("abc") in FALLBACK_HOOKS
    assert len({fallback_hook(f"id{i}") for i in range(50)}) > 1


@responses.activate
def test_gemini_answer_is_used():
    responses.post(GEMINI, json=gemini_reply({"hook": "he stole a jet", "title": "He stole a jet 😭"}))
    texts = call()
    assert texts == Texts(hook="HE STOLE A JET", title="He stole a jet 😭", source="gemini")
    request = responses.calls[0].request
    assert request.headers["x-goog-api-key"] == "KEY"
    body = json.loads(request.body)
    prompt = body["contents"][0]["parts"][0]["text"]
    assert "no way he just did that bro" in prompt and "xQc" in prompt
    assert body["generationConfig"]["responseMimeType"] == "application/json"


@responses.activate
def test_gemini_answer_inside_code_fences_is_understood():
    fenced = '```json\n{"hook": "COPS GAVE UP", "title": "The cops gave up"}\n```'
    responses.post(GEMINI, json=gemini_reply(fenced))
    assert call().hook == "COPS GAVE UP"


@responses.activate
def test_falls_back_to_pollinations_when_gemini_fails():
    responses.post(GEMINI, status=429)
    responses.post(writer.POLLINATIONS_URL, json=pollinations_reply({"hook": "NO WAY", "title": "No way"}))
    assert call() == Texts(hook="NO WAY", title="No way", source="pollinations")


@responses.activate
def test_without_key_goes_straight_to_pollinations():
    responses.post(writer.POLLINATIONS_URL, json=pollinations_reply({"hook": "NO WAY", "title": "No way"}))
    assert call(api_key="").source == "pollinations"
    assert len(responses.calls) == 1


@responses.activate
def test_invalid_hook_from_gemini_tries_the_next_writer():
    responses.post(GEMINI, json=gemini_reply({"hook": "", "title": "x"}))
    responses.post(writer.POLLINATIONS_URL, json=pollinations_reply({"hook": "BIG MISTAKE", "title": "t"}))
    assert call().hook == "BIG MISTAKE"


@responses.activate
def test_everything_failing_uses_the_fixed_list():
    responses.post(GEMINI, body=requests.ConnectionError("down"))
    responses.post(writer.POLLINATIONS_URL, body="not json")
    texts = call()
    assert texts == Texts(hook=fallback_hook("Clip1"), title=None, source="fallback")


@responses.activate
def test_bad_title_keeps_the_good_hook():
    responses.post(GEMINI, json=gemini_reply({"hook": "HE CRASHED", "title": "#gta6"}))
    assert call() == Texts(hook="HE CRASHED", title=None, source="gemini")


@responses.activate
def test_long_transcripts_are_trimmed_in_the_prompt():
    responses.post(GEMINI, json=gemini_reply({"hook": "HE CRASHED", "title": "t"}))
    call(transcript="word " * 2000)
    prompt = json.loads(responses.calls[0].request.body)["contents"][0]["parts"][0]["text"]
    assert len(prompt) < 4000
