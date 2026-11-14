import logging
from email import message_from_bytes

import pytest
import requests
import responses
from urllib3.exceptions import MaxRetryError, NewConnectionError

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


def never_connected():
    """O erro que o requests dá quando a ligação nem chega a abrir."""
    reason = NewConnectionError(None, "connection refused")
    return requests.ConnectionError(MaxRetryError(None, "/sendVideo", reason))


@pytest.mark.parametrize("error", [requests.ConnectTimeout("slow"), never_connected()])
@responses.activate
def test_video_that_certainly_did_not_leave_raises_publish_error(item, error):
    responses.add(responses.POST, f"{BASE}/sendVideo", body=error)
    with pytest.raises(PublishError):
        TelegramPublisher(TOKEN, "999").publish(item)
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "error", [requests.ReadTimeout("no answer"), requests.ConnectionError("reset by peer")]
)
@responses.activate
def test_video_with_unknown_outcome_is_not_retried_and_says_so(item, error, caplog):
    """Sem resposta depois do envio, o Telegram pode já ter entregue o vídeo:
    repetir duplicava-o. Conta como entregue e avisa na segunda mensagem."""
    responses.add(responses.POST, f"{BASE}/sendVideo", body=error)
    responses.add(responses.POST, f"{BASE}/sendMessage", json={"ok": True})
    with caplog.at_level(logging.WARNING):
        TelegramPublisher(TOKEN, "999").publish(item)
    text = requests.utils.unquote(responses.calls[1].request.body.replace("+", " "))
    assert "pode não ter chegado" in text
    assert "Abc" in caplog.text


@responses.activate
def test_token_never_appears_in_error_message_or_logs(item, caplog):
    responses.add(
        responses.POST,
        f"{BASE}/sendVideo",
        body=requests.ConnectTimeout(f"failed for url {BASE}/sendVideo"),
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(PublishError) as info:
        TelegramPublisher(TOKEN, "999").publish(item)
    assert TOKEN not in str(info.value)
    assert TOKEN not in caplog.text


@responses.activate
def test_check_passes_when_the_bot_can_see_the_chat():
    responses.add(responses.POST, f"{BASE}/getChat", json={"ok": True, "result": {"id": 999}})
    TelegramPublisher(TOKEN, "999").check()
    assert "chat_id=999" in responses.calls[0].request.body


@pytest.mark.parametrize(
    "status, description, fragment",
    [
        (400, "Bad Request: chat not found", "TELEGRAM_CHAT_ID"),
        (401, "Unauthorized", "TELEGRAM_BOT_TOKEN"),
        (403, "Forbidden: bot was blocked by the user", "bloqueado"),
    ],
)
@responses.activate
def test_check_explains_what_is_misconfigured(status, description, fragment):
    responses.add(
        responses.POST, f"{BASE}/getChat", json={"ok": False, "description": description}, status=status
    )
    with pytest.raises(PublishError, match=fragment) as info:
        TelegramPublisher(TOKEN, "999").check()
    assert TOKEN not in str(info.value)


def test_missing_video_file_raises_publish_error(item):
    item.video_path.unlink()
    with pytest.raises(PublishError):
        TelegramPublisher(TOKEN, "999").publish(item)


@pytest.fixture
def item_with_cover(item, tmp_path):
    cover = tmp_path / "Abc_cover.jpg"
    cover.write_bytes(b"\xff\xd8 fake jpeg")
    return RenderedClip(item.clip, item.video_path, "TITLE", "DESC", cover)


@responses.activate
def test_telegram_sends_cover_before_the_video(item_with_cover):
    for method in ("sendPhoto", "sendVideo", "sendMessage"):
        responses.add(responses.POST, f"{BASE}/{method}", json={"ok": True})
    TelegramPublisher(TOKEN, "999").publish(item_with_cover)
    assert [call.request.url for call in responses.calls] == [
        f"{BASE}/sendPhoto",
        f"{BASE}/sendVideo",
        f"{BASE}/sendMessage",
    ]
    photo = multipart_fields(responses.calls[0].request)
    assert photo["photo"] == b"\xff\xd8 fake jpeg" and photo["chat_id"] == b"999"


@responses.activate
def test_cover_failure_does_not_stop_the_video(item_with_cover, caplog):
    responses.add(responses.POST, f"{BASE}/sendPhoto", status=400, json={"ok": False, "description": "x"})
    responses.add(responses.POST, f"{BASE}/sendVideo", json={"ok": True})
    responses.add(responses.POST, f"{BASE}/sendMessage", json={"ok": True})
    with caplog.at_level(logging.WARNING):
        TelegramPublisher(TOKEN, "999").publish(item_with_cover)
    assert responses.calls[1].request.url == f"{BASE}/sendVideo"
    assert "capa" in caplog.text
    assert TOKEN not in caplog.text


def test_local_publisher_copies_the_cover(item_with_cover, tmp_path):
    out = tmp_path / "out"
    LocalPublisher(out).publish(item_with_cover)
    assert (out / "Abc.jpg").read_bytes() == b"\xff\xd8 fake jpeg"
