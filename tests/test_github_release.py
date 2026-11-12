import json
import logging
from datetime import timedelta

import pytest
import requests
import responses

from clipper.models import RenderedClip
from clipper.publishers.base import PublishError
from clipper.publishers.github_release import GitHubReleasePublisher
from tests.helpers import NOW, clip

TOKEN = "ghs_SECRETTOKEN"
REPO = "bieis-stack/gta6-clipper"
API = f"https://api.github.com/repos/{REPO}"
UPLOADS = f"https://uploads.github.com/repos/{REPO}/releases/7/assets"
RELEASE = {"id": 7, "upload_url": UPLOADS + "{?name,label}", "assets": []}


@pytest.fixture
def item(tmp_path):
    video = tmp_path / "Abc_final.mp4"
    video.write_bytes(b"fake video bytes")
    return RenderedClip(clip("Abc", views=42), video, "TITLE", "DESC line\n#GTA6")


def publisher():
    return GitHubReleasePublisher(TOKEN, REPO)


@responses.activate
def test_publish_creates_a_release_and_attaches_the_video(item):
    responses.add(responses.POST, f"{API}/releases", json=RELEASE, status=201)
    responses.add(responses.POST, UPLOADS, json={"id": 1}, status=201)
    publisher().publish(item)

    create, upload = responses.calls[0].request, responses.calls[1].request
    assert create.headers["Authorization"] == f"Bearer {TOKEN}"
    sent = json.loads(create.body)
    assert sent["tag_name"] == "clip-Abc" and sent["name"] == "TITLE"
    assert "TITLE" in sent["body"] and "DESC line\n#GTA6" in sent["body"]
    assert "42 visualizações" in sent["body"] and "https://clips.twitch.tv/Abc" in sent["body"]
    assert upload.url == UPLOADS + "?name=Abc.mp4"
    assert upload.headers["Content-Type"] == "video/mp4"
    sent_video = upload.body if isinstance(upload.body, bytes) else upload.body.read()
    assert sent_video == b"fake video bytes"


@responses.activate
def test_retry_after_a_lost_answer_does_not_upload_the_video_twice(item):
    """A release já existe e já tem o vídeo: nada a fazer, e não é erro."""
    responses.add(responses.POST, f"{API}/releases", json={"message": "Validation Failed"}, status=422)
    existing = {**RELEASE, "assets": [{"name": "Abc.mp4"}]}
    responses.add(responses.GET, f"{API}/releases/tags/clip-Abc", json=existing)
    publisher().publish(item)
    assert len(responses.calls) == 2


@responses.activate
def test_retry_reuses_a_release_left_without_its_video(item):
    responses.add(responses.POST, f"{API}/releases", json={"message": "Validation Failed"}, status=422)
    responses.add(responses.GET, f"{API}/releases/tags/clip-Abc", json=RELEASE)
    responses.add(responses.POST, UPLOADS, json={"id": 1}, status=201)
    publisher().publish(item)
    assert responses.calls[2].request.url == UPLOADS + "?name=Abc.mp4"


@responses.activate
def test_upload_failure_raises_publish_error(item):
    responses.add(responses.POST, f"{API}/releases", json=RELEASE, status=201)
    responses.add(responses.POST, UPLOADS, json={"message": "boom"}, status=500)
    with pytest.raises(PublishError, match="boom"):
        publisher().publish(item)


@responses.activate
def test_refused_release_explains_and_hides_the_token(item):
    responses.add(
        responses.POST, f"{API}/releases", json={"message": "Resource not accessible"}, status=403
    )
    with pytest.raises(PublishError, match="Resource not accessible") as info:
        publisher().publish(item)
    assert TOKEN not in str(info.value)


@responses.activate
def test_network_error_raises_publish_error_without_the_token(item):
    responses.add(
        responses.POST, f"{API}/releases", body=requests.ConnectionError(f"Bearer {TOKEN} failed")
    )
    with pytest.raises(PublishError) as info:
        publisher().publish(item)
    assert TOKEN not in str(info.value)


def test_missing_video_file_raises_publish_error(item):
    item.video_path.unlink()
    with pytest.raises(PublishError):
        publisher().publish(item)


@responses.activate
def test_check_passes_when_the_repository_answers():
    responses.add(responses.GET, API, json={"full_name": REPO})
    publisher().check()


@responses.activate
def test_check_fails_when_the_repository_is_out_of_reach():
    responses.add(responses.GET, API, json={"message": "Bad credentials"}, status=401)
    with pytest.raises(PublishError, match="Bad credentials"):
        publisher().check()


def release(release_id, tag, days_old):
    return {"id": release_id, "tag_name": tag, "created_at": (NOW - timedelta(days=days_old)).isoformat()}


@responses.activate
def test_prune_deletes_only_old_clip_releases_and_their_tags():
    responses.add(
        responses.GET,
        f"{API}/releases",
        json=[release(1, "clip-old", 8), release(2, "clip-new", 1), release(3, "v1.0", 30)],
    )
    responses.add(responses.DELETE, f"{API}/releases/1", status=204)
    responses.add(responses.DELETE, f"{API}/git/refs/tags/clip-old", status=204)
    publisher().prune(NOW)
    deleted = [c.request.url for c in responses.calls if c.request.method == "DELETE"]
    assert deleted == [f"{API}/releases/1", f"{API}/git/refs/tags/clip-old"]


@responses.activate
def test_prune_never_raises(caplog):
    responses.add(responses.GET, f"{API}/releases", json={"message": "down"}, status=500)
    with caplog.at_level(logging.WARNING):
        publisher().prune(NOW)
    assert "limpar" in caplog.text
