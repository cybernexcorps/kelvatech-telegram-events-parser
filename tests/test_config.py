"""Config loading — channels.yaml validation + env-driven Config."""
import pytest

from events_parser.config import Config, load_channels


def _write(tmp_path, text):
    p = tmp_path / "channels.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_loads_channels_with_domain_tags(tmp_path):
    path = _write(tmp_path, """
channels:
  - handle: ai_chan
    domain: ai
  - handle: pr_chan
    domain: pr
""")
    assert load_channels(path) == [("ai_chan", "ai"), ("pr_chan", "pr")]


def test_strips_leading_at_from_handle(tmp_path):
    path = _write(tmp_path, "channels:\n  - handle: '@ai_chan'\n    domain: ai\n")
    assert load_channels(path) == [("ai_chan", "ai")]


def test_invalid_domain_fails_fast(tmp_path):
    path = _write(tmp_path, "channels:\n  - handle: x\n    domain: crypto\n")
    with pytest.raises(ValueError):
        load_channels(path)


def test_empty_config_fails_fast(tmp_path):
    path = _write(tmp_path, "channels: []\n")
    with pytest.raises(ValueError):
        load_channels(path)


def test_config_from_env_reads_tunables():
    env = {
        "TELEGRAM_TARGET_CHAT_ID": "142068037",
        "HORIZON_DAYS": "14",
        "SCAN_DAYS": "10",
        "SEND_ON_EMPTY": "false",
    }
    cfg = Config.from_env(env, channels=[("ai_chan", "ai")])
    assert cfg.target_chat_id == 142068037
    assert cfg.horizon_days == 14
    assert cfg.scan_days == 10
    assert cfg.send_on_empty is False
    assert cfg.channels == [("ai_chan", "ai")]
