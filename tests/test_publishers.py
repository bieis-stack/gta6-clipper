import logging
from email import message_from_bytes

import pytest
import requests
import responses

from clipper.models import RenderedClip
from clipper.publishers.base import PublishError
from clipper.publishers.local import LocalPublisher
from clipper.publishers.telegram import TelegramPublisher
from tests.helpers import clip

TOKEN = "123456:SECRET-TOKEN"
BASE = f"https://api.telegram.org/bot{TOKEN}"


@pytest.fixture
def item(tmp_path):
    video = tmp_path / "Abc_final.mp4"
    video.write_bytes(b"fake video bytes")
    return RenderedClip(clip("Abc", views=42), video, "TITLE", "DESC")


def multipart_fields(request):
    header = b"Content-Type: " + request.headers["Content-Type"].encode() + b"\r\n\r\n"
    message = message_from_bytes(header + request.body)
    return {
        part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
        for part in message.get_payload()
    }


def test_local_publisher_writes_video_and_text(item, tmp_path):
    out = tmp_path / "out"
    LocalPublisher(out).publish(item)
    assert (out / "Abc.mp4").read_bytes() == b"fake video bytes"
    assert (out / "Abc.txt").read_text(encoding="utf-8") == "TITLE\n\nDESC"


@responses.activate
def test_telegram_sends_video_then_details(item):
    responses.add(responses.POST, f"{BASE}/sendVideo", json={"ok": True})
    responses.add(responses.POST, f"{BASE}/sendMessage", json={"ok": True})
    TelegramPublisher(TOKEN, "999").publish(item)

    assert [call.request.url for call in responses.calls] == [
        f"{BASE}/sendVideo",
        f"{BASE}/sendMessage",
    ]
    video = multipart_fields(responses.calls[0].request)
    assert video["chat_id"] == b"999"
    assert video["caption"] == b"TITLE"
    assert video["supports_streaming"] == b"true"
    assert video["width"] == b"1080" and video["height"] == b"1920"
    assert video["video"] == b"fake video bytes"

    details = responses.calls[1].request
    body = dict(pair.split("=", 1) for pair in details.body.split("&"))
    text = requests.utils.unquote(body["text"].replace("+", " "))
    assert body["chat_id"] == "999" and body["parse_mode"] == "HTML"
    assert "<pre>DESC</pre>" in text
    assert "Shroud" in text
    assert "42 visualizações" in text
    assert "https://clips.twitch.tv/Abc" in text


@responses.activate
def test_telegram_escapes_html_in_description(item, tmp_path):
    responses.add(responses.POST, f"{BASE}/sendVideo", json={"ok": True})
    responses.add(responses.POST, f"{BASE}/sendMessage", json={"ok": True})
    risky = RenderedClip(item.clip, item.video_path, "TITLE", "a <b> & c")
    TelegramPublisher(TOKEN, "999").publish(risky)
    text = requests.utils.unquote(responses.calls[1].request.body.replace("+", " "))
    assert "<pre>a &lt;b&gt; &amp; c</pre>" in text


@responses.activate
def test_video_failure_raises_publish_error_and_skips_details(item):
    responses.add(
        responses.POST,
        f"{BASE}/sendVideo",
        json={"ok": False, "description": "Bad Request: chat not found"},
        status=400,
    )
    with pytest.raises(PublishError, match="chat not found"):
        TelegramPublisher(TOKEN, "999").publish(item)
    assert len(responses.calls) == 1


@responses.activate
def test_details_failure_after_video_does_not_raise(item, caplog):
    responses.add(responses.POST, f"{BASE}/sendVideo", json={"ok": True})
    responses.add(responses.POST, f"{BASE}/sendMessage", json={"ok": False}, status=500)
    with caplog.at_level(logging.WARNING):
        TelegramPublisher(TOKEN, "999").publish(item)
    assert "descrição" in caplog.text


@responses.activate
def test_network_error_raises_publish_error(item):
    responses.add(responses.POST, f"{BASE}/sendVideo", body=requests.ConnectionError("down"))
    with pytest.raises(PublishError):
        TelegramPublisher(TOKEN, "999").publish(item)


@responses.activate
def test_token_never_appears_in_error_message_or_logs(item, caplog):
    responses.add(
        responses.POST,
        f"{BASE}/sendVideo",
        body=requests.ConnectionError(f"failed for url {BASE}/sendVideo"),
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(PublishError) as info:
        TelegramPublisher(TOKEN, "999").publish(item)
    assert TOKEN not in str(info.value)
    assert TOKEN not in caplog.text


def test_missing_video_file_raises_publish_error(item):
    item.video_path.unlink()
    with pytest.raises(PublishError):
        TelegramPublisher(TOKEN, "999").publish(item)
