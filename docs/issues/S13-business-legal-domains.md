# S13 — Business + Legal event domains (generalize the domain taxonomy)

**Type:** Feature (code + config) · **Parent:** docs/PRD.md · **Builds on:** S08 (subagents),
S10 (channels.yaml) · **Status:** spec

## Why

The digest was scoped to two domains, `ai` and `pr`, hardcoded in five places. A new
batch of candidate channels falls outside that taxonomy — general **business** event
feeds and a **legal** event feed. Rather than force-fit them into `pr` (which muddies
the "PR-события" section) we widen the taxonomy to add `business` and `legal`, and at
the same time replace the scattered hardcoding with a single ordered **domain registry**
so future domains are a one-line addition, not a five-file edit.

## What to build

1. Two new domains — `business` and `legal` — added to the validated domain set, the
   `Event.domain` type, the rendered digest sections, and the agentic subagent fan-out.
2. Five channels appended to `channels.yaml` (set decided below).
3. A single source of truth (`DOMAINS` registry) that `config`, `render`, and `agents`
   all read, so adding a domain later touches one definition.

### Channel set (decided)

| Handle | Domain | Notes (verified live on `t.me/s`, 2026-06-16) |
|---|---|---|
| `itevents` | `ai` (existing) | 19.7K subs, active daily, pure event feed (conf/meetup/forum/webinar/hackathon), AI/ML/DevOps heavy |
| `expomap` | `business` (new) | 14.8K, active, multi-source business-conference digest |
| `bizspbnews` | `business` (new) | 13.6K, active daily, SPb business events (networking/breakfasts) |
| `bizmosnews` | `business` (new) | 12K, active daily, Moscow business events |
| `aestheticsoflawevents` | `legal` (new) | 10.1K, active daily, lawyer webinars/conferences, many **free** |

**Rejected / dropped (do not add):**
- `itrussiaevents` — **rejected.** Description claims "IT events" but recent posts are
  off-topic political/conspiracy content; one post reads "Channel name was changed to
  «Мероприятия России в IT»" — a repurposed channel whose name no longer matches content.
- `productsense` — **dropped.** Low third-party event density: mostly promotes its own two
  annual conferences (ProductSense/PeopleSense) + editorial/podcast, not third-party events.
- `moscowbiznes` — **dropped** (earlier round). No posts since 2026-04-10 (stale) + ad-heavy.

**Skipped (already present in `channels.yaml`, would double-scan):**
`ITMeeting`, `iteventsrus`, `freeitevent`, `inter_comm`.

## Design

### Domain registry — single source of truth

Introduce an ordered registry mapping a domain code to its presentation + agent metadata.
Lives in `models.py` (alongside the `Domain` type) or a small `domains.py`:

```python
# domain code -> (digest section title, short RU label for agent prompts)
DOMAINS: dict[str, DomainSpec] = {
    "ai":       DomainSpec(section_title="🤖 События в сфере ИИ", ru_label="ИИ"),
    "pr":       DomainSpec(section_title="📣 PR-события",          ru_label="PR"),
    "business": DomainSpec(section_title="💼 Бизнес-события",      ru_label="бизнес"),
    "legal":    DomainSpec(section_title="⚖️ Юридические события", ru_label="юридические"),
}
```

Dict insertion order defines digest section order (ai → pr → business → legal → open).

### Touchpoints

| File | Change | Risk |
|---|---|---|
| `models.py` | Add `DOMAINS` registry + `DomainSpec`; extend `Domain` Literal to `"ai"\|"pr"\|"business"\|"legal"`. | low |
| `config.py` | `VALID_DOMAINS = set(DOMAINS)` (derive, stop hardcoding `{"ai","pr"}`). | low |
| `render.py` | Replace the hardcoded `ai`/`pr` section block (lines 71–79) with a loop over `DOMAINS`: one dated section per domain (title from registry), then the existing "open" section. | medium |
| `agents.py` | Extract a **pure** `build_subagent_specs(config)` → one `{name, description, system_prompt, tools?}` per domain *present in config*, driven by the registry + `_domain_channels`. `build_supervisor` consumes it. Generalize `async_subagent_specs` the same way. | **high — production path** |
| `agents.py` + `langgraph.json` | Add `business_events_graph` / `legal_events_graph` entrypoints (thin wrappers over the existing generic `_domain_graph`) and register them in `langgraph.json`. | low (preview path only) |
| `channels.yaml` | Append the 5 entries with comments; update header comment to `ai\|pr\|business\|legal`. | low |
| `__main__.py` | *(optional)* extend the `--demo` fixture to emit one event per domain so `--demo --dry-run` visibly renders all sections. | low |
| `docs/MANUAL.md` | Update domain set (`§ channels.yaml`), the channel list, the subagent diagram (2 → N subagents), and the "verified live" date. | low |
| `CONTEXT.md` | Update if it enumerates the domain set. | low |

### Why the agentic path is the critical bit

Production runs the **agentic** path (`USE_AGENTS=true` on the cron host →
`AgentDigestService.run` → `build_supervisor`). The supervisor currently delegates only
to `ai-events` / `pr-events`, so a `business`/`legal` channel added to config would be
**collected by no subagent** and its section would always render empty — a silent gap.
Generalizing `build_supervisor` to fan out one subagent per configured domain is therefore
load-bearing, not cosmetic. The deterministic path (`run_digest`/`_collect`) is already
domain-generic (it loops all `config.channels` and stamps each event with its channel's
domain), so `--no-agents` needs no change.

### Testability

The heavy imports (`langchain_core` in `_build_tools`, `deepagents` in `build_supervisor`)
stay lazy. The new fan-out logic is extracted as the **pure** `build_subagent_specs(config)`
returning plain dicts, so it is unit-tested with no langchain/deepagents. `render`, `config`,
`models` changes are already pure.

## Acceptance criteria

- [ ] `business` and `legal` accepted by `load_channels`; an unknown domain still fails fast.
- [ ] The 5 channels are present in `channels.yaml` with correct domains; no duplicates of
      the four already-present handles.
- [ ] `render_digest` emits a 💼 Бизнес-события section and an ⚖️ Юридические события section
      for dated events of those domains, in registry order; empty domains render nothing;
      undated events of any domain still land in the "open" section.
- [ ] `build_subagent_specs(config)` returns exactly one subagent per domain *present in
      config*, each owning only its domain's channels, prompt naming that domain.
- [ ] `async_subagent_specs` and `langgraph.json` list a graph per domain.
- [ ] Full unit suite green (excluding `test_app.py`, which is gated on the un-installed
      `runtime` extra and is untouched by this change).
- [ ] `docs/MANUAL.md` reflects the new domains, channels, and N-subagent fan-out.

## Out of scope / follow-ups

- **Standalone-repo sync + VPS deploy.** This branch lands the change in the **mono-repo**
  (`cybernexcorps/kelvatech`). Production runs the **standalone** repo
  (`cybernexcorps/kelvatech-telegram-events-parser`, deployed via tar/rsync →
  `docker compose build`). Reaching production requires syncing `channels.yaml` + the code
  into the standalone repo and redeploying — tracked separately, the user triggers it.
- **LangGraph deployment registration.** The async-subagent-server form is a deepagents 0.5
  preview path the in-container deploy does not use; the `langgraph.json` graph entries are
  added for consistency but are not exercised by the VPS cron.

## Blocked by

None. Channel set and taxonomy already confirmed with the user.
