# LeadOps

LeadOps is a local-first CLI for precision lead curation.

It is built for independents and small studios that care more about `lead quality` than lead volume. LeadOps runs a bounded daily pass, scores candidates against your actual business model, drafts a small review packet, and stops before any external action.

It is intentionally not:

- a CRM
- a mass outreach tool
- an autonomous sales agent
- an auto-send email system

## What It Does

- keeps pipeline state locally in SQLite
- dedupes targets across days and sources
- runs bounded web discovery
- supports repeatable discovery tracks
- uses structured LLM assessment and drafting
- learns from approve / reject / snooze decisions
- writes a dated daily brief and plain-text digest
- can send that digest by SMTP
- can install a macOS `launchd` job for a daily run

## How It Works

LeadOps follows a small, opinionated loop:

1. retrieve a limited set of candidate pages or search results
2. assess them against your actual fit criteria
3. rank and cap the output
4. draft a small daily packet
5. wait for human review

The design goal is simple:

`surface a few leads you would genuinely want to follow up on`

## Design Principles

- `Precision over volume`
- `Local-first state`
- `Human review before send`
- `Deterministic orchestration`
- `LLMs for judgment, not control flow`
- `Small packets instead of giant lists`

## Install

LeadOps currently targets Python `3.12+`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

You can also use the repo-local wrappers without installing console scripts globally:

```bash
./bin/leadops --help
```

## Quick Start

Create a workspace:

```bash
leadops init-workspace ~/leadops-workspace
```

That creates:

- `leadops.toml`
- `var/leadops.db`
- `outbox/`
- `cache/`

Run a simple daily pass with the built-in mock provider:

```bash
leadops run-daily --workspace ~/leadops-workspace
```

Review the outputs in:

- `outbox/YYYY-MM-DD/daily-brief.md`
- `outbox/YYYY-MM-DD/daily-brief.json`
- `outbox/YYYY-MM-DD/daily-digest.txt`

## Common Commands

```bash
leadops init-workspace ~/leadops-workspace
leadops list-tracks
leadops discover-track --workspace ~/leadops-workspace --track daily --per-query-limit 2
leadops run-daily --workspace ~/leadops-workspace
leadops list-targets --workspace ~/leadops-workspace
leadops mark-status --workspace ~/leadops-workspace 12 approved --reason "Exactly the kind of work I want"
leadops feedback-summary --workspace ~/leadops-workspace
```

### Manual Intake

Add a target directly:

```bash
leadops add-target \
  --workspace ~/leadops-workspace \
  --kind founder \
  --name "Example Startup" \
  --url "https://example.com" \
  --source "manual" \
  --notes "Founder-led team with an early product and no obvious engineering org."
```

Or ingest a public page:

```bash
leadops ingest-url \
  --workspace ~/leadops-workspace \
  --kind founder \
  --url "https://example.com"
```

### Discovery

Run one bounded search:

```bash
leadops discover-web \
  --workspace ~/leadops-workspace \
  --kind founder \
  --query "founder launched beta workflow SaaS no engineering team" \
  --limit 3
```

Or use the built-in tracks:

```bash
leadops list-tracks

leadops discover-track \
  --workspace ~/leadops-workspace \
  --track connectors \
  --per-query-limit 2
```

Available tracks currently include:

- `connectors`
- `founders`
- `daily`

These tracks are intentionally narrow. The tool is trying to find usable targets, not to build a giant list.

## Provider Setup

LeadOps supports two provider roles:

- `llm`
  - assessment, ranking rationale, outreach drafting
- `discovery`
  - bounded candidate discovery from the public web

Provider modes currently supported:

- `mock`
- `command`
- `none` for discovery when disabled

The `command` mode lets you plug in a model-backed adapter that accepts JSON on `stdin` and returns JSON on `stdout`.

## OpenAI Example

LeadOps includes helper scripts for OpenAI-backed assessment and discovery.

Example workspace config:

```toml
[llm]
provider = "command"
command = "leadops-openai-bridge --model gpt-5.4 --reasoning-effort high --max-output-tokens 4000"
timeout_seconds = 90

[discovery]
provider = "command"
command = "leadops-openai-discover --model gpt-5.4 --reasoning-effort low --max-output-tokens 5000"
timeout_seconds = 180
```

Then set `OPENAI_API_KEY` in your shell before running discovery or daily curation.

## Status Workflow

Targets move through a small workflow:

- `candidate`
- `approved`
- `rejected`
- `sent`
- `replied`
- `snoozed`
- `archived`

When you include a reason with `mark-status`, recent accepted and avoided patterns are fed back into discovery and assessment prompts.

If you set a future `--followup-date` on a `candidate` or `approved` target, LeadOps treats that as a real snooze and keeps the target out of the daily packet until that date.

Example:

```bash
leadops mark-status \
  --workspace ~/leadops-workspace \
  12 rejected \
  --reason "Too advisory and not enough direct build ownership"

leadops mark-status \
  --workspace ~/leadops-workspace \
  12 candidate \
  --followup-date 2026-04-16 \
  --reason "Snooze until next week"
```

## Email Digest

LeadOps always writes a plain-text digest. It can also send that digest through SMTP.

Example:

```toml
[email]
mode = "smtp"
host = "smtp.example.com"
port = 587
username = "you@example.com"
password_env = "LEADOPS_SMTP_PASSWORD"
from_addr = "you@example.com"
to_addr = "you@example.com"
starttls = true
send_on_run = false
```

Send a previously generated digest:

```bash
leadops send-digest \
  --workspace ~/leadops-workspace \
  --date 2026-04-08
```

Or send it directly after a run:

```bash
leadops run-daily \
  --workspace ~/leadops-workspace \
  --send-digest
```

## Scheduling

On macOS, LeadOps can generate and install a `launchd` job for a daily run.

Preview the plist:

```bash
leadops print-launchd --workspace ~/leadops-workspace
```

Install the default job:

```bash
leadops install-launchd --workspace ~/leadops-workspace
```

Current defaults:

- label: `dev.leadops.daily`
- time: `08:00` local time
- tracks: `connectors` and `founders`
- per-query limit: `2`
- digest send: enabled

## Development

Run the test suite:

```bash
python3 -B -m unittest discover -s tests -v
```

The repo is intentionally small. If you change behavior, keep the public docs and CLI help aligned with the code.

## Project Status

LeadOps is still early. The current focus is on:

- stronger discovery quality
- better ranking from human feedback
- cleaner review packets
- reliable local operation

## Non-Goals

LeadOps should not drift into:

- autonomous outreach
- automatic sending or posting by default
- generic CRM bloat
- “growth hacking” features
- unbounded scraping or spam automation
- a full web app unless the CLI model clearly stops being enough
