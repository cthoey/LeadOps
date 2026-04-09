# LeadOps

LeadOps is a small local tool for daily lead curation.

It is intentionally not a web app and not an autonomous outreach agent.

The product thesis is:

- optimize for precision, not volume
- surface only a few leads you would actually want to follow up on
- keep state locally with SQLite
- use a pluggable reasoning provider for assessment and drafting
- stop at a human review boundary

## Current MVP

The first cut includes:

- workspace bootstrap
- SQLite state
- target dedupe
- discovery query-run tracking
- candidate import
- public URL ingestion with lightweight page extraction
- bounded web discovery ingestion
- daily packet generation
- pluggable assessment provider
- packaged OpenAI bridge for structured assessment
- packaged OpenAI bridge for structured web discovery
- markdown and JSON packet output

Retrieval is intentionally bounded. The tool supports targeted web discovery, but it still stops at a tiny human-reviewed packet instead of turning into an autonomous outreach engine.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

If you do not want to install it yet, use the repo-local wrappers:

```bash
./bin/leadops --help
```

## Quick Start

Create a workspace:

```bash
leadops init-workspace /absolute/path/to/workspace
```

Add a candidate manually:

```bash
leadops add-target \
  --workspace /absolute/path/to/workspace \
  --kind founder \
  --name "Example Startup" \
  --url "https://example.com" \
  --source "manual" \
  --notes "Founder-led startup with a beta product and no visible engineering team."
```

Or ingest a public page directly:

```bash
leadops ingest-url \
  --workspace /absolute/path/to/workspace \
  --kind founder \
  --url "https://example.com"
```

Or run a bounded discovery pass and ingest only the strongest candidates it finds:

```bash
leadops discover-web \
  --workspace /absolute/path/to/workspace \
  --kind founder \
  --query "founder launched beta workflow SaaS no engineering team" \
  --limit 3
```

Or use a built-in hyper-aligned track:

```bash
leadops list-tracks

leadops discover-track \
  --workspace /absolute/path/to/workspace \
  --track connectors \
  --per-query-limit 2
```

Run the daily pass:

```bash
leadops run-daily --workspace /absolute/path/to/workspace
```

You can also run discovery and the packet in one step:

```bash
leadops run-daily \
  --workspace /absolute/path/to/workspace \
  --discover-track daily \
  --discover-per-query-limit 2
```

Record review decisions with reasons so future discovery and scoring can learn from them:

```bash
leadops mark-status \
  --workspace /absolute/path/to/workspace \
  12 rejected \
  --reason "Too advisory and not enough direct build ownership"

leadops feedback-summary --workspace /absolute/path/to/workspace
```

The daily brief will be written to:

- `outbox/YYYY-MM-DD/daily-brief.md`
- `outbox/YYYY-MM-DD/daily-brief.json`
- `outbox/YYYY-MM-DD/daily-digest.txt`

## Email Digest

LeadOps writes a plain-text digest for every packet. It can also send that digest by SMTP when explicitly configured.

Example config:

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
  --workspace /absolute/path/to/workspace \
  --date 2026-04-08
```

Or send it directly after a packet run:

```bash
leadops run-daily \
  --workspace /absolute/path/to/workspace \
  --send-digest
```

## Scheduling

On macOS, LeadOps can generate and install a `launchd` agent for a morning daily run.

Preview the plist:

```bash
leadops print-launchd \
  --workspace /absolute/path/to/workspace
```

Install the default daily agent:

```bash
leadops install-launchd \
  --workspace /absolute/path/to/workspace
```

Defaults:

- label: `com.choey.leadops.daily`
- time: `08:00` local time
- discovery tracks: `connectors` and `founders`
- per-query limit: `2`
- digest sending: enabled

The scheduled job runs the repo-local `bin/leadops-daily` wrapper, which sources `~/.zprofile` before executing `run-daily`. That keeps your API key and SMTP password available to the scheduled run.

## Provider Contract

LeadOps supports two assessment provider modes:

- `mock`: local heuristic scoring for offline development
- `command`: run an external command that accepts JSON on `stdin` and returns JSON on `stdout`

The `command` mode is the integration point for GPT-backed assessment and drafting.

The provider receives a payload like:

```json
{
  "profile": {
    "offer": "Independent product engineer helping founders...",
    "hard_rejects": ["staff augmentation", "employment-style work"]
  },
  "target": {
    "id": 12,
    "kind": "founder",
    "name": "Example Startup",
    "url": "https://example.com",
    "source": "manual",
    "notes": "Founder-led startup with beta product..."
  }
}
```

The provider must return JSON matching the shape documented in `src/leadops/models.py`.

## Discovery Contract

Bounded discovery is configured separately from daily assessment.

The discovery command receives a payload like:

```json
{
  "profile": {
    "offer": "Independent product engineer helping founders...",
    "hard_rejects": ["staff augmentation", "employment-style work"]
  },
  "search": {
    "kind": "founder",
    "query": "founder launched beta workflow SaaS no engineering team",
    "limit": 3
  }
}
```

It must return JSON with a top-level `candidates` array matching the discovery types in `src/leadops/models.py`.

## Built-In Discovery Tracks

LeadOps now ships with a few query families for repeatable high-precision discovery:

- `connectors`
  - founder-facing product design and UX studios
  - brand/web studios likely to stop before engineering
- `founders`
  - very early product or waitlist-stage founders
  - prototype and early-access teams that look closer to build work than maintenance
- `daily`
  - one compact mixed track for a single daily pass

The tracks are intentionally narrow. They are meant to produce a few usable leads, not a giant list.

### OpenAI Bridge

If you want to use OpenAI directly without writing your own bridge, set the workspace config to:

```toml
[llm]
provider = "command"
command = "leadops-openai-bridge --model gpt-5.4 --reasoning-effort high --max-output-tokens 4000"
timeout_seconds = 90
```

For discovery, add:

```toml
[discovery]
provider = "command"
command = "leadops-openai-discover --model gpt-5.4 --reasoning-effort low --max-output-tokens 5000"
timeout_seconds = 180
```

Then set `OPENAI_API_KEY` before running `leadops discover-web` or `leadops run-daily`.

The bridges use the Responses API with structured JSON output so the model is constrained to the LeadOps assessment and discovery schemas. The discovery bridge also enables OpenAI web search, so the model can search the public web before returning candidates.

`gpt-5.4` is the recommended first live model for this tool because the official model docs say:

- if you are not sure where to start, use `gpt-5.4`
- `gpt-5.4` supports structured outputs
- `gpt-5.4-pro` does not support structured outputs and may take several minutes to finish

If you installed LeadOps with `pip install -e .`, the helper bridges are also available as console scripts:

- `leadops-openai-bridge`
- `leadops-openai-discover`

## Status Workflow

Supported target statuses:

- `candidate`
- `approved`
- `rejected`
- `sent`
- `replied`
- `snoozed`
- `archived`

The daily pass only surfaces:

- eligible new candidates
- follow-ups due today or earlier

When you use `mark-status --reason`, LeadOps carries those recent liked and avoided patterns back into both discovery and assessment prompts. That keeps the packet biased toward what you actually want instead of just what looks startup-shaped.

## Next Steps

Planned next layers:

- dossier assembly across multiple pages
- follow-up draft specialization
- richer rejection-reason handling in ranking
- delivery options beyond SMTP
