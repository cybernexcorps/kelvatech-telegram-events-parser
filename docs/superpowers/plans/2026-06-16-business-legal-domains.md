# Business + Legal Event Domains — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `business` and `legal` event domains (plus the `itevents` AI channel) by replacing the five hardcoded `ai`/`pr` sites with one ordered `DOMAINS` registry that config, render, and the agentic fan-out all read.

**Architecture:** A single `DOMAINS` registry in `models.py` maps each domain code to its digest-section title and a short RU agent label. `config.VALID_DOMAINS` derives from it; `render_digest` iterates it to emit one section per domain; the agentic supervisor fans out one subagent per domain *present in config* via a new pure `build_subagent_specs(config)`. The deterministic path is already domain-generic, so it needs no change.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, pytest. Agentic path uses LangChain Deep Agents (lazy-imported); the new fan-out logic is pure (no langchain/deepagents) so it unit-tests without them.

**Spec:** `docs/issues/S13-business-legal-domains.md`

---

## Test runner (Windows worktree)

The worktree has no `.venv` (gitignored). Reuse the main checkout's interpreter, which already has `pytest`, `pydantic`, `pyyaml`, and `langchain-core`:

```bash
VENV_PY="D:/Downloads/SynologyDrive/kelvatech/SharedWorkspace/Dev-Platform/agents/kelvatech-telegram-events-parser/.venv/Scripts/python.exe"
cd "D:/Downloads/SynologyDrive/kelvatech/SharedWorkspace/.worktrees/add-event-domains/Dev-Platform/agents/kelvatech-telegram-events-parser"
```

Run the suite (excluding `test_app.py`, gated on the un-installed `runtime` extra — `app.py` is untouched here):

```bash
PYTHONPATH=src "$VENV_PY" -m pytest -q --ignore=tests/test_app.py
```

Baseline before starting: **78 passed, 2 skipped**.
Every commit must carry the trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/events_parser/models.py` | Domain types + the `DOMAINS` registry (single source of truth). | Add `DomainSpec` + `DOMAINS`; extend `Domain` Literal. |
| `src/events_parser/config.py` | Channel/env config; domain validation. | Derive `VALID_DOMAINS` from `DOMAINS`. |
| `src/events_parser/render.py` | Pure RU digest renderer. | Loop `DOMAINS` for sections instead of hardcoded ai/pr. |
| `src/events_parser/agents.py` | Agentic supervisor + subagent fan-out (prod path). | Add pure `build_subagent_specs`; rewire supervisor + async specs + per-domain graphs. |
| `channels.yaml` | Scanned channel list. | Append 5 entries; update header comment. |
| `langgraph.json` | Async-deploy graph registry (preview path). | Register `business_events` + `legal_events` graphs. |
| `src/events_parser/__main__.py` | CLI incl. `--demo`. | *(Task 6, optional)* demo emits one event per domain. |
| `docs/MANUAL.md`, `CONTEXT.md` | Operator docs. | Reflect new domains, channels, N-subagent fan-out. |
| `tests/test_config.py`, `tests/test_render.py`, `tests/test_agents.py` | Unit tests. | New tests per task. |

---

### Task 1: Domain registry + validation

**Files:**
- Modify: `src/events_parser/models.py` (lines 8, 14 + insert registry)
- Modify: `src/events_parser/config.py:10-12`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_business_and_legal_are_valid_domains(tmp_path):
    path = _write(tmp_path, """
channels:
  - handle: biz_chan
    domain: business
  - handle: law_chan
    domain: legal
""")
    assert load_channels(path) == [("biz_chan", "business"), ("law_chan", "legal")]


def test_valid_domains_derive_from_registry():
    from events_parser.config import VALID_DOMAINS
    from events_parser.models import DOMAINS

    assert VALID_DOMAINS == set(DOMAINS)
    assert {"ai", "pr", "business", "legal"} <= set(DOMAINS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest tests/test_config.py -q`
Expected: `test_business_and_legal_are_valid_domains` FAILS (ValueError: invalid domain 'business'); `test_valid_domains_derive_from_registry` FAILS (ImportError: cannot import name 'DOMAINS').

- [ ] **Step 3: Add the registry to `models.py`**

Change the import on line 8 from:

```python
from typing import Literal, Optional
```
to:
```python
from typing import Literal, NamedTuple, Optional
```

Replace the type-alias block (lines 12-14):

```python
EventType = Literal["conference", "meetup", "webinar", "other"]
CostStatus = Literal["free", "paid", "unknown"]
Domain = Literal["ai", "pr"]
```
with:
```python
EventType = Literal["conference", "meetup", "webinar", "other"]
CostStatus = Literal["free", "paid", "unknown"]
Domain = Literal["ai", "pr", "business", "legal"]


class DomainSpec(NamedTuple):
    """Presentation + agent metadata for one event domain."""

    section_title: str  # digest section header (render.py)
    ru_label: str       # short RU label injected into the subagent prompt (agents.py)


# Single source of truth for the domain taxonomy. Insertion order defines the
# order of sections in the rendered digest. Adding a domain here is all that the
# deterministic path, the renderer, and the agentic fan-out need.
DOMAINS: dict[str, DomainSpec] = {
    "ai":       DomainSpec("🤖 События в сфере ИИ", "ИИ"),
    "pr":       DomainSpec("📣 PR-события", "PR"),
    "business": DomainSpec("💼 Бизнес-события", "бизнес"),
    "legal":    DomainSpec("⚖️ Юридические события", "юридические"),
}
```

- [ ] **Step 4: Derive `VALID_DOMAINS` in `config.py`**

Change lines 10-12 from:

```python
# (handle, domain) pairs — domain routes a channel to its subagent.
ChannelSpec = tuple[str, str]
VALID_DOMAINS = {"ai", "pr"}
```
to:
```python
from .models import DOMAINS

# (handle, domain) pairs — domain routes a channel to its subagent.
ChannelSpec = tuple[str, str]
VALID_DOMAINS = set(DOMAINS)  # single source of truth: events_parser.models.DOMAINS
```

(Place the `from .models import DOMAINS` line with the other imports near the top — after `import yaml` on line 8 — rather than mid-file; the snippet above shows intent. No circular import: `models.py` does not import `config.py`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest tests/test_config.py -q`
Expected: PASS (including the existing `test_invalid_domain_fails_fast` — `crypto` is still rejected).

- [ ] **Step 6: Commit**

```bash
git add src/events_parser/models.py src/events_parser/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
Add DOMAINS registry; add business + legal domains

VALID_DOMAINS now derives from models.DOMAINS (was a hardcoded {ai,pr}).
Domain Literal extended with business + legal.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Renderer emits one section per domain

**Files:**
- Modify: `src/events_parser/render.py:18` (import) and `:67-83` (`render_digest`)
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render.py`:

```python
def test_business_and_legal_events_render_under_their_sections():
    out = render_digest([
        _ev("Бизнес-завтрак", domain="business"),
        _ev("Вебинар для юристов", domain="legal"),
    ], now=NOW)
    assert "💼 Бизнес-события" in out
    assert "⚖️ Юридические события" in out
    assert "Бизнес-завтрак" in out
    assert "Вебинар для юристов" in out


def test_sections_render_in_registry_order():
    out = render_digest([
        _ev("L", domain="legal"),
        _ev("A", domain="ai"),
        _ev("B", domain="business"),
        _ev("P", domain="pr"),
    ], now=NOW)
    assert (out.find("🤖 События в сфере ИИ")
            < out.find("📣 PR-события")
            < out.find("💼 Бизнес-события")
            < out.find("⚖️ Юридические события"))


def test_domain_with_no_events_renders_no_section():
    out = render_digest([_ev("Только ИИ", domain="ai")], now=NOW)
    assert "💼 Бизнес-события" not in out
    assert "⚖️ Юридические события" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest tests/test_render.py -q`
Expected: `test_business_and_legal_events_render_under_their_sections` and `test_sections_render_in_registry_order` FAIL (business/legal sections not emitted).

- [ ] **Step 3: Generalize the renderer**

Change the import on line 18 from:

```python
from .models import Event
```
to:
```python
from .models import DOMAINS, Event
```

Replace the body of `render_digest` (lines 67-83) from:

```python
def render_digest(events: list[Event], *, now: datetime) -> str:
    if not events:
        return EMPTY_MESSAGE

    ai = [e for e in events if e.domain == "ai" and e.start_date is not None]
    pr = [e for e in events if e.domain == "pr" and e.start_date is not None]
    open_ = [e for e in events if e.start_date is None]

    week = f"{now.day} {_RU_MONTHS[now.month]} {now.year}"
    out: list[str] = [f"<b>Дайджест событий — неделя от {week}</b>", ""]
    out += _section("🤖 События в сфере ИИ", ai)
    out += _section("📣 PR-события", pr)
    out += _section("🔓 Открытые события и вебинары по запросу", open_)

    if len(out) <= 2:  # only the header, nothing rendered
        return EMPTY_MESSAGE
    return "\n".join(out).rstrip() + "\n"
```
to:
```python
def render_digest(events: list[Event], *, now: datetime) -> str:
    if not events:
        return EMPTY_MESSAGE

    week = f"{now.day} {_RU_MONTHS[now.month]} {now.year}"
    out: list[str] = [f"<b>Дайджест событий — неделя от {week}</b>", ""]

    # One dated section per domain, in registry order; undated events of any
    # domain collapse into the shared "open / by-request" section below.
    for domain, spec in DOMAINS.items():
        dated = [e for e in events if e.domain == domain and e.start_date is not None]
        out += _section(spec.section_title, dated)

    open_ = [e for e in events if e.start_date is None]
    out += _section("🔓 Открытые события и вебинары по запросу", open_)

    if len(out) <= 2:  # only the header, nothing rendered
        return EMPTY_MESSAGE
    return "\n".join(out).rstrip() + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest tests/test_render.py -q`
Expected: PASS (including the pre-existing `test_ai_and_pr_events_go_under_their_section_headers`).

- [ ] **Step 5: Commit**

```bash
git add src/events_parser/render.py tests/test_render.py
git commit -m "$(cat <<'EOF'
render_digest iterates DOMAINS for sections

Adds 💼 Бизнес-события + ⚖️ Юридические события sections in registry order;
empty domains render nothing; the open section is unchanged.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Agentic fan-out — one subagent per configured domain

**Files:**
- Modify: `src/events_parser/agents.py` (add `build_subagent_specs`; rewrite `build_supervisor` lines 97-145; generalize `async_subagent_specs` lines 148-158; add two graph entrypoints after line 191)
- Test: `tests/test_agents.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agents.py`:

```python
from events_parser.agents import build_subagent_specs
from events_parser.config import Config


def test_build_subagent_specs_one_per_configured_domain():
    config = Config(channels=[
        ("ai1", "ai"), ("pr1", "pr"),
        ("biz1", "business"), ("biz2", "business"),
        ("law1", "legal"),
    ])
    specs = build_subagent_specs(config)

    assert [s["name"] for s in specs] == [
        "ai-events", "pr-events", "business-events", "legal-events"
    ]
    biz = next(s for s in specs if s["name"] == "business-events")
    assert "biz1" in biz["system_prompt"] and "biz2" in biz["system_prompt"]
    assert "ai1" not in biz["system_prompt"]
    assert "domain='business'" in biz["system_prompt"]
    # pure path attaches no tools unless asked
    assert "tools" not in biz


def test_build_subagent_specs_skips_domains_with_no_channels():
    config = Config(channels=[("ai1", "ai")])
    specs = build_subagent_specs(config)
    assert [s["name"] for s in specs] == ["ai-events"]


def test_async_subagent_specs_cover_every_domain():
    from events_parser.agents import async_subagent_specs
    from events_parser.models import DOMAINS

    graph_ids = {s["graphId"] for s in async_subagent_specs()}
    assert graph_ids == {f"{d}_events" for d in DOMAINS}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest tests/test_agents.py -q`
Expected: the three new tests FAIL (ImportError: cannot import name 'build_subagent_specs'); the two existing `_build_tools` tests still PASS.

- [ ] **Step 3: Add `build_subagent_specs` and rewire**

In `src/events_parser/agents.py`, immediately after `_domain_channels` (line 94), add:

```python
def build_subagent_specs(config: Config, tools=None) -> list[dict]:
    """One subagent spec per domain *present in config*, driven by models.DOMAINS.

    Pure — imports neither deepagents nor langchain — so the fan-out is unit-testable.
    ``tools`` is attached only when provided (the live build_supervisor path).
    """
    from .models import DOMAINS

    specs: list[dict] = []
    for domain, spec in DOMAINS.items():
        channels = _domain_channels(config, domain)
        if not channels:
            continue
        sub = {
            "name": f"{domain}-events",
            "description": f"Scans {domain}-field Telegram channels and records upcoming events.",
            "system_prompt": (
                f"Ты отвечаешь за поиск мероприятий ({spec.ru_label}). Для КАЖДОГО из этих "
                f"каналов вызови extract_and_record_events(channel, domain='{domain}'): {channels}. "
                "После обработки всех каналов кратко отчитайся, сколько событий записано."
            ),
        }
        if tools is not None:
            sub["tools"] = tools
        specs.append(sub)
    return specs
```

Replace `build_supervisor` (lines 97-145) from its current body with:

```python
def build_supervisor(collector: EventCollector, config: Config,
                     env: Optional[Mapping[str, str]] = None):
    """Construct the Deep Agents supervisor with one subagent per configured domain."""
    from deepagents import create_deep_agent

    env = env if env is not None else os.environ
    tools = _build_tools(collector, config.scan_days)
    model = _agent_model(env)

    subagents = build_subagent_specs(config, tools=tools)
    delegate = ", ".join(s["name"] for s in subagents)

    # create_deep_agent bundles the planning (TodoList) and Filesystem middleware by
    # default, so per-domain planning + large-payload offload are active without explicit
    # wiring. Additionally, the tools return only short snippets ([id] text[:120]), so raw
    # t.me/s HTML never enters the supervisor's context window in the first place.
    return create_deep_agent(
        model=model,
        tools=tools,
        subagents=subagents,
        system_prompt=(
            "Ты — супервайзер еженедельного дайджеста мероприятий. Делегируй сбор событий "
            f"субагентам ({delegate}), затем сообщи, что сбор завершён. Не пиши сам "
            "дайджест — его соберёт детерминированный пайплайн из записанных событий."
        ),
    )
```

Replace `async_subagent_specs` (lines 148-158) from its current body with:

```python
def async_subagent_specs(env: Optional[Mapping[str, str]] = None) -> list[dict]:
    """Production async-subagent-server specs (deepagents 0.5 preview), one per domain.

    Co-deployed (no url) over ASGI under a LangGraph deployment; each graphId must
    be registered in langgraph.json. Used instead of inline subagents when running
    under LangSmith Deployments / `langgraph dev`.
    """
    from .models import DOMAINS

    return [
        {"name": f"{d}-events", "description": f"{d}-field event scanner", "graphId": f"{d}_events"}
        for d in DOMAINS
    ]
```

After `pr_events_graph` (line 191), add:

```python
def business_events_graph():
    """LangGraph entrypoint for the async business-events subagent server."""
    return _domain_graph("business")


def legal_events_graph():
    """LangGraph entrypoint for the async legal-events subagent server."""
    return _domain_graph("legal")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest tests/test_agents.py -q`
Expected: PASS (all five — three new + two pre-existing).

- [ ] **Step 5: Commit**

```bash
git add src/events_parser/agents.py tests/test_agents.py
git commit -m "$(cat <<'EOF'
Generalize agentic fan-out to one subagent per configured domain

build_subagent_specs (pure, registry-driven) replaces the hardcoded
ai-events/pr-events list; build_supervisor + async_subagent_specs consume it;
adds business_events_graph + legal_events_graph entrypoints.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add the channels + register the graphs

**Files:**
- Modify: `channels.yaml`
- Modify: `langgraph.json`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing integrity test**

Append to `tests/test_config.py` (add `from pathlib import Path` to the imports at the top if not present):

```python
def test_repo_channels_yaml_set_is_correct():
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    specs = load_channels(str(repo_root / "channels.yaml"))
    handles = [h for h, _ in specs]
    by_domain: dict[str, set[str]] = {}
    for h, d in specs:
        by_domain.setdefault(d, set()).add(h)

    assert "itevents" in by_domain.get("ai", set())
    assert {"expomap", "bizspbnews", "bizmosnews"} <= by_domain.get("business", set())
    assert "aestheticsoflawevents" in by_domain.get("legal", set())
    for rejected in ("itrussiaevents", "productsense", "moscowbiznes"):
        assert rejected not in handles
    assert len(handles) == len(set(handles)), "duplicate channel handles"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest tests/test_config.py::test_repo_channels_yaml_set_is_correct -q`
Expected: FAIL (assert "itevents" in ... — the channels aren't added yet).

- [ ] **Step 3: Append the channels to `channels.yaml`**

Change the header comment (lines 1-2) from:

```yaml
# Channels scanned for the weekly digest. `domain` (ai|pr) routes a channel to its
# subagent and digest section. All verified live on t.me/s (2026-06-07).
```
to:
```yaml
# Channels scanned for the weekly digest. `domain` (ai|pr|business|legal) routes a
# channel to its subagent and digest section. All verified live on t.me/s (2026-06-16).
```

Add `itevents` under the AI block (after the `ai_machinelearning_big_data` entry, line 12):

```yaml
  - handle: itevents                      # IT Events — конференции/митапы/форумы/вебинары/хакатоны (AI/ML/DevOps-heavy)
    domain: ai
```

Append two new blocks after the PR block (after line 22):

```yaml

  # --- Business-field events ---
  - handle: expomap                       # Expomap — дайджест бизнес-конференций/форумов/выставок
    domain: business
  - handle: bizspbnews                    # Бизнес-мероприятия Санкт-Петербурга (конференции/нетворкинги)
    domain: business
  - handle: bizmosnews                    # Бизнес-мероприятия Москвы (конференции/бизнес-завтраки)
    domain: business

  # --- Legal-field events ---
  - handle: aestheticsoflawevents         # Мероприятия для юристов — вебинары/конференции (много бесплатных)
    domain: legal
```

- [ ] **Step 4: Register the new graphs in `langgraph.json`**

Replace the `graphs` object so it reads:

```json
  "graphs": {
    "supervisor": "./src/events_parser/agents.py:supervisor_graph",
    "ai_events": "./src/events_parser/agents.py:ai_events_graph",
    "pr_events": "./src/events_parser/agents.py:pr_events_graph",
    "business_events": "./src/events_parser/agents.py:business_events_graph",
    "legal_events": "./src/events_parser/agents.py:legal_events_graph"
  },
```

- [ ] **Step 5: Run the test (and the full suite) to verify pass**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest -q --ignore=tests/test_app.py`
Expected: PASS — all green, new total = baseline + new tests.

- [ ] **Step 6: Commit**

```bash
git add channels.yaml langgraph.json tests/test_config.py
git commit -m "$(cat <<'EOF'
Add itevents (ai) + business/legal channels; register domain graphs

channels.yaml: itevents(ai); expomap/bizspbnews/bizmosnews(business);
aestheticsoflawevents(legal). langgraph.json registers business_events +
legal_events. Integrity test guards the set + no-duplicate invariant.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Update operator docs

**Files:**
- Modify: `docs/MANUAL.md`
- Modify: `CONTEXT.md` (only if it enumerates the domain set)

- [ ] **Step 1: Update the `channels.yaml` section in `docs/MANUAL.md`**

Around lines 526-534, replace:

```markdown
A list of `{handle, domain}` entries; `domain` ∈ `{ai, pr}`. Validated on load —
an empty list, a missing handle, or an invalid domain raises immediately. Editing
this file (mounted read-only into the container) adds/removes channels with **no
code change**. Current set (verified live 2026-06-07):

- **AI:** `ITMeeting`, `freeitevent`, `iteventsrus`, `ai_machinelearning_big_data`
- **PR:** `companiesrbc`, `inter_comm`, `prexplore`, `roscongress`
```
with:
```markdown
A list of `{handle, domain}` entries; `domain` ∈ `{ai, pr, business, legal}` (the set
is `events_parser.models.DOMAINS`). Validated on load — an empty list, a missing
handle, or an invalid domain raises immediately. Editing this file (mounted read-only
into the container) adds/removes channels with **no code change**. Adding a *new
domain* is a one-line addition to `DOMAINS`. Current set (verified live 2026-06-16):

- **AI:** `ITMeeting`, `freeitevent`, `iteventsrus`, `ai_machinelearning_big_data`, `itevents`
- **PR:** `companiesrbc`, `inter_comm`, `prexplore`, `roscongress`
- **Business:** `expomap`, `bizspbnews`, `bizmosnews`
- **Legal:** `aestheticsoflawevents`
```

- [ ] **Step 2: Update the subagent-fan-out description**

Around lines 157-163, replace the sentence describing two subagents:

```markdown
A Deep Agents **supervisor** delegates to two subagents, `ai-events` and
`pr-events`, each owning its domain's channels. The subagents call the
```
with:
```markdown
A Deep Agents **supervisor** delegates to one subagent per configured domain
(`ai-events`, `pr-events`, `business-events`, `legal-events`), each owning its
domain's channels (built by `build_subagent_specs` from `models.DOMAINS`). The
subagents call the
```

Around lines 378-382, replace the diagram:

```markdown
            supervisor (create_deep_agent)
            ├── ai-events  subagent  → owns domain=="ai" channels
            └── pr-events  subagent  → owns domain=="pr" channels
```
with:
```markdown
            supervisor (create_deep_agent)
            ├── ai-events        subagent → owns domain=="ai" channels
            ├── pr-events        subagent → owns domain=="pr" channels
            ├── business-events  subagent → owns domain=="business" channels
            └── legal-events     subagent → owns domain=="legal" channels
```

- [ ] **Step 3: Check `CONTEXT.md`**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest -q --ignore=tests/test_app.py` is not relevant here; instead grep:
`grep -n "ai, pr\|{ai\|domain" CONTEXT.md` — if `CONTEXT.md` lists the domains as only ai/pr, update it to `ai, pr, business, legal` and mention the `DOMAINS` registry. If it does not enumerate domains, leave it unchanged.

- [ ] **Step 4: Commit**

```bash
git add docs/MANUAL.md CONTEXT.md
git commit -m "$(cat <<'EOF'
docs: business + legal domains, N-subagent fan-out

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

(If `CONTEXT.md` was not changed, drop it from the `git add`.)

---

### Task 6 (optional): demo renders every section

Cosmetic — gives `--demo --dry-run` a visible all-sections digest for manual eyeballing. Skip if undesired. No unit test (demo path).

**Files:**
- Modify: `src/events_parser/__main__.py` (the `_demo_deps` extractor ~lines 52-58 and `_run_demo` config ~line 75)

- [ ] **Step 1: Make the demo extractor vary the title per channel**

In `_demo_deps`, change the `_Extractor.extract` return so each channel yields a distinct title (otherwise identical events dedupe to one):

```python
    class _Extractor:
        def extract(self, post):
            return [Event(title=f"Демо-событие ({post.channel})", event_type="webinar",
                          host="Kelva", cost_status="free",
                          start_date=datetime.now(timezone.utc) + timedelta(days=7),
                          source_channel=post.channel, source_post_url=post.permalink,
                          source_post_dt=post.dt)]
```

(The `domain="ai"` kwarg is dropped — the orchestrator stamps each event with its channel's configured domain, so the demo event's domain follows the channel below.)

- [ ] **Step 2: Give the demo config a channel in every domain**

In `_run_demo`, replace the `cfg` line:

```python
    cfg = Config(channels=[
        ("demo_ai_chan", "ai"),
        ("demo_pr_chan", "pr"),
        ("demo_biz_chan", "business"),
        ("demo_law_chan", "legal"),
    ], target_chat_id=0, dry_run=dry_run)
```

- [ ] **Step 3: Run the demo and eyeball all four sections**

Run: `PYTHONPATH=src "$VENV_PY" -m events_parser --demo --dry-run`
Expected: the printed digest contains 🤖 ИИ, 📣 PR, 💼 Бизнес, and ⚖️ Юридические sections, each with one demo event.

- [ ] **Step 4: Commit**

```bash
git add src/events_parser/__main__.py
git commit -m "$(cat <<'EOF'
demo: render one event per domain for visual verification

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Final verification

- [ ] **Full suite green**

Run: `PYTHONPATH=src "$VENV_PY" -m pytest -q --ignore=tests/test_app.py`
Expected: all PASS (baseline 78 + the new tests), 2 skipped.

- [ ] **Pipeline smoke (no secrets)**

Run: `PYTHONPATH=src "$VENV_PY" -m events_parser --demo --dry-run`
Expected: a digest renders without error (all four domain sections if Task 6 was done; AI-only otherwise).

- [ ] **Ship** — hand back to the user's "ship it" flow (push → PR → merge → switch to main worktree → pull → remove feature worktree → delete branch). Then the **separate follow-up**: sync `channels.yaml` + code into the standalone repo `cybernexcorps/kelvatech-telegram-events-parser` and redeploy the VPS — not part of this branch.
