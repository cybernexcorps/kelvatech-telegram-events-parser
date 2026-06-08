"""S07 — Telegram delivery: message splitting + Bot API send (no live network)."""
import pytest

from events_parser.notify import TelegramNotifier, split_message


def test_short_message_is_one_chunk():
    assert split_message("hello", limit=4096) == ["hello"]


def test_long_message_splits_under_limit_and_preserves_content():
    text = "\n".join(f"line {i}" for i in range(1000))
    chunks = split_message(text, limit=200)
    assert all(len(c) <= 200 for c in chunks)
    assert len(chunks) > 1
    # rejoining recovers every line (split happens on newlines)
    rejoined = "\n".join(chunks).replace("\n\n", "\n")
    for i in range(1000):
        assert f"line {i}" in rejoined


def test_single_line_longer_than_limit_is_hard_split():
    text = "x" * 500
    chunks = split_message(text, limit=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == text


def test_send_calls_bot_api_once_per_chunk_with_chat_and_token():
    calls = []

    def fake_post(url, json):
        calls.append((url, json))

    notifier = TelegramNotifier(token="TKN", http_post=fake_post)
    notifier.send(142068037, "a\n" * 5000)  # forces multiple chunks

    assert len(calls) >= 2
    for url, payload in calls:
        assert "botTKN/sendMessage" in url
        assert payload["chat_id"] == 142068037
        assert payload["text"]


def test_send_short_message_single_call():
    calls = []
    TelegramNotifier(token="T", http_post=lambda url, json: calls.append(json)).send(1, "hi")
    assert len(calls) == 1
    assert calls[0]["text"] == "hi"
