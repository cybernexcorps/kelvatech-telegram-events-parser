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


def test_use_agents_defaults_per_caller_when_env_absent():
    # USE_AGENTS used to be read raw at each entry point with divergent defaults
    # (cron app.py=true, CLI __main__.py=false). The split is intentional — local
    # iteration stays on the cheap deterministic path, prod runs the agentic path —
    # so Config resolves it from a caller-supplied default, one place, one parser.
    assert Config.from_env({}, channels=[], use_agents_default=True).use_agents is True
    assert Config.from_env({}, channels=[], use_agents_default=False).use_agents is False


def test_use_agents_env_overrides_default_with_one_truthiness_rule():
    # Regression: the cron path honored "1"/"yes"/"on" but the CLI honored only
    # "true", so USE_AGENTS=1 silently meant different things per entry point.
    # One parser (_as_bool) now governs both, overriding the caller default.
    for truthy in ("1", "true", "yes", "on", "TRUE"):
        assert Config.from_env({"USE_AGENTS": truthy}, use_agents_default=False).use_agents is True
    for falsy in ("0", "false", "no", "off"):
        assert Config.from_env({"USE_AGENTS": falsy}, use_agents_default=True).use_agents is False
