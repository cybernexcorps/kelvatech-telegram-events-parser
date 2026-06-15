# Domain Docs

How the engineering skills should consume this repo's domain documentation when
exploring the codebase. **Layout: single-context.**

## Before exploring, read these

- **`CONTEXT.md`** at the repo root (the glossary), and
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.

If any of these files don't exist yet, **proceed silently**. Don't flag their absence;
don't suggest creating them upfront. The producer skill (`/grill-with-docs`) creates
them lazily when terms or decisions actually get resolved.

## File structure (single-context)

```
/  (Dev-Platform/agents/kelvatech-telegram-events-parser/)
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-....md
│   └── 0002-....md
└── src/events_parser/
```

There is no `CONTEXT-MAP.md` — this subproject is one bounded context.

## Use the glossary's vocabulary

When your output names a domain concept (issue title, refactor proposal, hypothesis,
test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the
glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're
inventing language the project doesn't use (reconsider) or there's a real gap (note it
for `/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently
overriding:

> _Contradicts ADR-0002 (...) — but worth reopening because…_
