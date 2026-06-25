"""FastAPI host — the /digest acknowledgement reply routes through the one
Telegram-send seam (TelegramNotifier), so it can't drift from the digest/alert
send paths. Regression target: the parse_mode 400 that the hand-rolled _reply
used to be able to reintroduce.

These exercise _reply directly with an injected app.state.replier, bypassing the
lifespan/startup wiring (which needs real secrets).
"""
from events_parser.app import _reply, app
from events_parser.notify import TelegramNotifier


class _SpyReplier:
    def __init__(self):
        self.sent = []

    def send(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_reply_delegates_verbatim_to_the_replier():
    # _reply's whole job is to forward (chat_id, text) to the shared send seam.
    spy = _SpyReplier()
    app.state.replier = spy

    _reply(142068037, "готово")

    assert spy.sent == [(142068037, "готово")]


def test_reply_through_plain_text_replier_omits_parse_mode():
    # End-to-end through the real notifier wired as the lifespan builds it
    # (parse_mode=None) — the parse_mode 400 class can no longer reappear in _reply.
    calls = []
    app.state.replier = TelegramNotifier("T", http_post=lambda url, json: calls.append(json),
                                          parse_mode=None)

    _reply(142068037, "готово")

    assert len(calls) == 1
    assert calls[0]["chat_id"] == 142068037 and calls[0]["text"] == "готово"
    assert "parse_mode" not in calls[0]


def test_reply_is_best_effort_and_never_raises():
    def boom(url, json):
        raise RuntimeError("Telegram down")

    app.state.replier = TelegramNotifier("T", http_post=boom)
    _reply(1, "x")  # a failed ack must never break the webhook handler


def test_reply_noops_when_replier_unset():
    app.state.replier = None
    _reply(1, "x")  # no bot token configured → silent no-op, no network


def test_configure_logging_silences_httpx_to_keep_bot_token_out_of_logs():
    """The Telegram Bot API carries the token in the request *path*
    (/bot<TOKEN>/sendMessage), so httpx's INFO "HTTP Request: POST <url>" line leaks the
    token into docker logs. _configure_logging must raise httpx (and telethon) above INFO
    so that line never prints, while leaving our own logging at INFO."""
    import logging

    from events_parser.app import _configure_logging

    # Pre-dirty the loggers to INFO to prove the function actually raises them.
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("telethon").setLevel(logging.INFO)

    _configure_logging()

    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert not logging.getLogger("telethon").isEnabledFor(logging.INFO)
    # our own logs stay at INFO
    assert logging.getLogger("events_parser").isEnabledFor(logging.INFO)
