"""Composition root — build_config threads the per-caller use_agents default into Config."""
from events_parser.factory import build_config


def _channels(tmp_path):
    p = tmp_path / "channels.yaml"
    p.write_text("channels:\n  - handle: ai_chan\n    domain: ai\n", encoding="utf-8")
    return str(p)


def test_build_config_threads_use_agents_default(tmp_path):
    env = {"CHANNELS_CONFIG": _channels(tmp_path)}
    assert build_config(env, use_agents_default=True).use_agents is True
    assert build_config(env, use_agents_default=False).use_agents is False


def test_build_config_env_use_agents_overrides_default(tmp_path):
    # Same USE_AGENTS value, same result, regardless of which entry point built it.
    env = {"CHANNELS_CONFIG": _channels(tmp_path), "USE_AGENTS": "0"}
    assert build_config(env, use_agents_default=True).use_agents is False
