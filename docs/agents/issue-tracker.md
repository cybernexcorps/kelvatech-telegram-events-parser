# Issue tracker: GitHub

Issues and PRDs for this project live as GitHub issues in the **standalone repo**
[`cybernexcorps/kelvatech-telegram-events-parser`](https://github.com/cybernexcorps/kelvatech-telegram-events-parser).
Use the `gh` CLI for all operations.

## ⚠️ Always pin the repo with `-R`

This subproject is **mirrored** into the `cybernexcorps/kelvatech` mono-repo, and
the working copy under `Dev-Platform/agents/kelvatech-telegram-events-parser/` is
tracked by that mono-repo. So `git remote -v` here resolves to `cybernexcorps/kelvatech`,
**not** the standalone parser repo. `gh`'s automatic repo inference would target the
wrong place.

**Every `gh` command MUST pass `-R cybernexcorps/kelvatech-telegram-events-parser`.**

The repo is **public** — never put secrets (bot tokens, `TELEGRAM_SESSION`, chat IDs,
API keys) in issue titles, bodies, or comments. Crash tracebacks with paths/line
numbers are fine.

## Conventions

- **Create an issue**: `gh issue create -R cybernexcorps/kelvatech-telegram-events-parser --title "..." --body "..."` (heredoc for multi-line bodies).
- **Read an issue**: `gh issue view <number> -R cybernexcorps/kelvatech-telegram-events-parser --comments`.
- **List issues**: `gh issue list -R cybernexcorps/kelvatech-telegram-events-parser --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` / `--state` filters.
- **Comment**: `gh issue comment <number> -R cybernexcorps/kelvatech-telegram-events-parser --body "..."`
- **Apply / remove labels**: `gh issue edit <number> -R cybernexcorps/kelvatech-telegram-events-parser --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> -R cybernexcorps/kelvatech-telegram-events-parser --comment "..."`

## When a skill says "publish to the issue tracker"

Create a GitHub issue in `cybernexcorps/kelvatech-telegram-events-parser`.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> -R cybernexcorps/kelvatech-telegram-events-parser --comments`.
