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
- supports named lead-finding approaches
- supports repeatable discovery tracks
- uses structured LLM assessment and drafting
- learns from approve / reject / snooze decisions
- writes a dated daily brief plus text and HTML digests
- can send those digests as a multipart SMTP email
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
- `outbox/YYYY-MM-DD/daily-digest.html`

Those filenames always point at the latest packet for that date. If you rerun the same date more than once, LeadOps also keeps versioned snapshots alongside them, such as `daily-brief.v2.md`.

## Common Commands

```bash
leadops init-workspace ~/leadops-workspace
leadops list-approaches
leadops list-tracks
# Founder Needs Builder
leadops discover-approach --workspace ~/leadops-workspace --approach builder_need
leadops discover-track --workspace ~/leadops-workspace --track daily --per-query-limit 2
# Default daily stance is Founder Needs Builder
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
  --query "founder roadmap prototype no engineering team product build" \
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

Or use a built-in approach:

```bash
leadops list-approaches

# Founder Needs Builder
leadops discover-approach \
  --workspace ~/leadops-workspace \
  --approach builder_need

# Public Founder Asks
leadops run-daily \
  --workspace ~/leadops-workspace \
  --approach place_watch
```

Available tracks currently include:

- `connectors`
- `founders`
- `builder_need`
- `place_watch`
- `daily`

These tracks are intentionally narrow. The tool is trying to find usable targets, not to build a giant list.

## Lead-Finding Approaches

LeadOps keeps the business profile fixed and lets you vary the search strategy.

In other words:

- the `profile` answers: who are you trying to work with?
- the `approach` answers: how are you trying to find them?

This keeps the feature small. It is not a multi-ICP engine. It is a way to test different lead-finding strategies for the same business.

### `Founder + Connector Mix` (`early_product`)

Best for the broadest aligned search.

Strategy:

- search both founder-adjacent connectors and founder-side roadmap/prototype transitions
- accept existing products only when they still show a real implementation transition
- favor roadmap-to-build and prototype-to-launch work over maintenance or hiring

Use it when:

- you want the current balanced motion
- you still want connectors in the mix
- you want a wider pool without abandoning precision

### `Founder Needs Builder` (`builder_need`)

Best for the narrowest direct-fit search.

Strategy:

- look for a real product idea, roadmap, or prototype plus visible evidence of a build gap
- heavily discount already-live products that do not also show a next-phase ownership need
- prefer tiny teams with no obvious engineering depth
- bias the packet toward founders first, with only a small number of connectors

Use it when:

- you want fewer, harsher direct-founder candidates
- you care more about visible builder need than general early-product similarity
- you want the packet to feel closer to “they may actually need me now”

### `Public Founder Asks` (`place_watch`)

Best for monitoring explicit asks on specific public surfaces.

Strategy:

- watch a few places where founders sometimes publicly ask for help turning a roadmap, prototype, or rough product into something real
- favor freshness and direct asks
- reject cofounder, hiring, equity-only, or role-fill opportunities aggressively

Use it when:

- you want to test a time-sensitive monitoring strategy
- you want explicit need signals, even if the channel is noisier

### Feature Strategy

The point of approaches is experimentation.

LeadOps should help you answer:

- which search strategy surfaces leads you genuinely want to follow up on?
- which strategy creates the least noise?
- which strategy produces real conversations?

The intended comparison loop is:

1. run different approaches for the same business
2. approve or reject surfaced leads
3. track replies and conversations by approach
4. keep the strategies that produce the best actual outcomes

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

LeadOps always writes both:

- `outbox/YYYY-MM-DD/daily-digest.txt`
- `outbox/YYYY-MM-DD/daily-digest.html`

When SMTP is configured, it sends a multipart email with the plain-text digest as the fallback and the HTML digest as the primary rendered version.

Each digest also includes a compact `Run context` block so you can see:

- which approach produced the packet
- what that approach was prioritizing
- what it was trying to reject

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
leadops print-launchd \
  --workspace ~/leadops-workspace \
  --approach builder_need \
  --time 08:00 \
  --time 11:00 \
  --time 14:00 \
  --time 17:00
```

Install the default job:

```bash
leadops install-launchd \
  --workspace ~/leadops-workspace \
  --approach builder_need \
  --time 08:00 \
  --time 11:00 \
  --time 14:00 \
  --time 17:00
```

Current defaults when you do not pass `--time`:

- label: `dev.leadops.daily`
- time: `08:00` local time
- approach: `Founder Needs Builder` (`builder_need`)
- per-query limit: `2`
- digest send: enabled

You can repeat `--time HH:MM` to schedule multiple local runs per day while keeping each run bounded and high-signal.

You can still add extra `--discover-track` flags on top of the selected approach, but the normal path is:

- choose one approach
- let that approach define the default track mix
- compare results by approach over time

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
