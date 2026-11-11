from datetime import UTC, datetime

import pytest
import responses

from clipper.models import Clip
from clipper.twitch import TwitchAuthError, TwitchClient, TwitchError, User

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API = "https://api.twitch.tv/helix"
USER = User("1", "shroud", "Shroud")
START = datetime(2026, 11, 19, 4, 0, tzinfo=UTC)
END = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)

RAW_CLIP = {
    "id": "Abc",
    "url": "https://clips.twitch.tv/Abc",
    "broadcaster_id": "1",
    "broadcaster_name": "Shroud",
    "creator_name": "viewer",
    "video_id": "v9",
    "game_id": "123",
    "title": "wow",
    "view_count": 42,
    "created_at": "2026-11-19T10:00:00Z",
    "duration": 29.5,
    "vod_offset": 1234,
}


def add_token(status=200):
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "tok", "expires_in": 5000000} if status == 200 else {"message": "bad"},
        status=status,
    )


def client():
    return TwitchClient("cid", "secret")


@responses.activate
def test_token_is_requested_once_and_sent_as_bearer():
    add_token()
    responses.add(responses.GET, f"{API}/games", json={"data": [{"id": "123"}]})
    c = client()
    c.get_game_id("X")
    c.get_game_id("X")
    token_calls = [call for call in responses.calls if call.request.url.startswith(TOKEN_URL)]
    assert len(token_calls) == 1
    assert "client_id=cid" in token_calls[0].request.body
    assert "grant_type=client_credentials" in token_calls[0].request.body
    api_request = responses.calls[-1].request
    assert api_request.headers["Authorization"] == "Bearer tok"
    assert api_request.headers["Client-Id"] == "cid"


@responses.activate
def test_bad_credentials_raise_auth_error():
    add_token(status=400)
    with pytest.raises(TwitchAuthError):
        client().get_game_id("X")


@responses.activate
def test_api_error_raises_twitch_error():
    add_token()
    responses.add(responses.GET, f"{API}/clips", json={"message": "boom"}, status=500)
    with pytest.raises(TwitchError) as info:
        client().get_clips(USER, START, END)
    assert not isinstance(info.value, TwitchAuthError)


@responses.activate
def test_rejected_token_raises_auth_error():
    add_token()
    responses.add(responses.GET, f"{API}/games", json={"message": "invalid"}, status=401)
    with pytest.raises(TwitchAuthError):
        client().get_game_id("X")


@responses.activate
def test_network_failure_raises_twitch_error():
    add_token()
    with pytest.raises(TwitchError):
        client().get_game_id("X")  # sem resposta registada → ConnectionError


@responses.activate
def test_errors_never_contain_the_secret():
    add_token(status=400)
    with pytest.raises(TwitchAuthError) as info:
        client().get_game_id("X")
    assert "secret" not in str(info.value)


@responses.activate
def test_get_game_id():
    add_token()
    responses.add(responses.GET, f"{API}/games", json={"data": [{"id": "123", "name": "X"}]})
    responses.add(responses.GET, f"{API}/games", json={"data": []})
    c = client()
    assert c.get_game_id("X") == "123"
    assert responses.calls[-1].request.params == {"name": "X"}
    assert c.get_game_id("Nope") is None


@responses.activate
def test_get_users_maps_by_lowercase_login_and_omits_unknown():
    add_token()
    responses.add(
        responses.GET,
        f"{API}/users",
        json={"data": [{"id": "1", "login": "shroud", "display_name": "Shroud"}]},
    )
    assert client().get_users(["Shroud", "ghost"]) == {"shroud": User("1", "shroud", "Shroud")}
    assert responses.calls[-1].request.url.endswith("/users?login=shroud&login=ghost")


@responses.activate
def test_get_users_without_logins_makes_no_request():
    assert client().get_users([]) == {}
    assert len(responses.calls) == 0


@responses.activate
def test_get_clips_parses_fields():
    add_token()
    responses.add(responses.GET, f"{API}/clips", json={"data": [RAW_CLIP], "pagination": {}})
    c = client().get_clips(USER, START, END)[0]
    assert c == Clip(
        id="Abc",
        url="https://clips.twitch.tv/Abc",
        broadcaster_id="1",
        broadcaster_login="shroud",
        broadcaster_name="Shroud",
        title="wow",
        game_id="123",
        view_count=42,
        created_at=datetime(2026, 11, 19, 10, 0, tzinfo=UTC),
        duration=29.5,
        video_id="v9",
        vod_offset=1234,
    )


@responses.activate
def test_get_clips_without_vod():
    add_token()
    raw = {**RAW_CLIP, "video_id": "", "vod_offset": None}
    responses.add(responses.GET, f"{API}/clips", json={"data": [raw], "pagination": {}})
    c = client().get_clips(USER, START, END)[0]
    assert c.video_id is None
    assert c.vod_offset is None


@responses.activate
def test_get_clips_sends_rfc3339_range():
    add_token()
    responses.add(responses.GET, f"{API}/clips", json={"data": [], "pagination": {}})
    assert client().get_clips(USER, START, END) == []
    assert responses.calls[-1].request.params == {
        "broadcaster_id": "1",
        "started_at": "2026-11-19T04:00:00Z",
        "ended_at": "2026-11-19T10:00:00Z",
        "first": "100",
    }


@responses.activate
def test_get_clips_follows_cursor_up_to_three_pages():
    add_token()
    for page in range(4):
        raw = {**RAW_CLIP, "id": f"c{page}"}
        responses.add(
            responses.GET,
            f"{API}/clips",
            json={"data": [raw], "pagination": {"cursor": f"cur{page}"}},
        )
    clips = client().get_clips(USER, START, END)
    clip_calls = [call for call in responses.calls if "/clips" in call.request.url]
    assert [c.id for c in clips] == ["c0", "c1", "c2"]
    assert len(clip_calls) == 3
    assert clip_calls[1].request.params["after"] == "cur0"
