"""S07 — Telegram delivery: message splitting + Bot API send (no live network)."""
import pytest

from events_parser.notify import TelegramNotifier, build_error_alerter, split_message


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


# --- Issue #4: dedicated error-bot alerter ---

def test_error_alerter_is_noop_when_env_unset():
    """No error-bot token/chat configured → alerting is a silent no-op (best-effort),
    never raising and never calling the network."""
    calls = []
    alert = build_error_alerter({}, http_post=lambda url, json: calls.append((url, json)))
    alert("something broke")  # must not raise
    assert calls == []


def test_error_alerter_sends_via_error_bot_when_configured():
    calls = []
    env = {"TELEGRAM_ERROR_BOT_TOKEN": "ERRTKN", "TELEGRAM_ERROR_CHAT_ID": "142068037"}
    alert = build_error_alerter(env, http_post=lambda url, json: calls.append((url, json)))

    alert("boom")

    assert len(calls) == 1
    url, payload = calls[0]
    assert "botERRTKN/sendMessage" in url
    assert payload["chat_id"] == 142068037
    assert payload["text"] == "boom"
    # plain-text alerts must NOT send parse_mode=None — Telegram 400s on a null
    # parse_mode ("unsupported parse_mode"). The key must be omitted entirely.
    assert "parse_mode" not in payload
