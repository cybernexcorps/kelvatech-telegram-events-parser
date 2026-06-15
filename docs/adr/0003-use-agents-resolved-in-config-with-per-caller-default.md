# Resolve USE_AGENTS in Config with a per-entry-point default

`USE_AGENTS` selects the agentic path over the deterministic path. It used to be read
raw at each entry point, and the two reads disagreed on **two** axes:

| Entry point | default | accepted truthy values |
|---|---|---|
| cron host (`app.py`) | `true` | `1`, `true`, `yes` |
| CLI (`__main__.py`) | `false` | only `true` |

So the same env var meant different things depending on who started the process:
`USE_AGENTS=1` turned the agentic path **on** under the cron host but was silently
**ignored** by the CLI. `Config` already owned every other runtime knob (and already had
the correct `_as_bool` parser accepting `1/true/yes/on`), but this one knob escaped it —
and its escape was the bug.

**Decision:** `Config` owns `use_agents`, resolved once via `_as_bool` from a
caller-supplied `use_agents_default`. Both entry points read `config.use_agents`; neither
reads the env directly. The **parsing** is now unified — one truthiness rule everywhere.

The **default split is deliberately kept**: the cron host passes `use_agents_default=True`
(production runs the agentic path), the CLI passes `False` (local iteration stays on the
cheap deterministic path so a `--live --dry-run` does not burn Yandex agentic tokens). The
CLI `--agents`/`--no-agents` flag still overrides the resolved default.

The footgun was never the *differing defaults* — those serve genuinely different operators.
It was the *differing parsers* and the reads *bypassing* `Config`.

**Consequence / constraint:** do not "consolidate" the two defaults into a single value — a
future architecture pass will be tempted to, seeing `use_agents_default=True` in one place
and `False` in another. The split is intentional and now lives as one explicit argument at
each call site, routed through one parser in `Config.from_env`. Revisit only if the agentic
path becomes cheap enough that local dev wants it on by default.

_Tests assert the per-caller default and the one-truthiness-rule regression at
`Config.from_env`, and that `build_config` threads the default through while an env value
overrides it._
