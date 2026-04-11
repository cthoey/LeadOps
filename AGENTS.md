# AGENTS.md

Guidance for humans and coding agents working in this repository.

## Project Shape

LeadOps is a small local tool for precision lead curation.

It is intentionally:

- a CLI-first application
- local-first
- SQLite-backed
- packet-driven
- human-reviewed

It is intentionally not:

- a CRM platform
- a full web app
- an autonomous outreach agent
- a spam engine
- an auto-send system

## Source Of Truth

The code and tests in this repository are the source of truth.

If README examples, release notes, or comments drift from the actual command surface, update them to match the implementation.

## Core Principles

- `Precision over volume`
  - The system should maximize the percentage of surfaced leads that the user actually wants to review or contact.
- `Human review boundary`
  - Discovery, scoring, and drafting may be automated. External actions should not happen by default.
- `Deterministic orchestration`
  - Scheduling, state transitions, dedupe, and packet assembly should remain explicit and testable.
- `LLMs as judgment engines`
  - Use models for bounded discovery, assessment, and drafting. Do not make them the control plane.
- `Keep the tool small`
  - Prefer a simple local workflow over dashboards, services, or architecture that the product does not need.
- `Business-agnostic core, business-specific configuration`
  - Keep the engine generic. Core concepts such as evidence, inference, freshness, queues, and qualification stages should work across many businesses.
  - Business-specific fit rules, thresholds, signal preferences, and disqualifiers should live in configuration, prompts, profiles, or retrieval presets rather than hard-coded engine assumptions.

## Public-Facing Hygiene

Assume this repository is public.

- Do not commit secrets, tokens, or real credentials.
- Avoid machine-specific paths in docs, tests, or defaults unless they are unavoidable test fixtures.
- Avoid personal labels, usernames, or host-specific values in defaults unless they are explicitly configurable.
- Keep README examples generic and copyable.

## Scope Boundaries

Be resistant to changes that push LeadOps toward:

- volume-first lead generation
- mass personalization
- automatic outreach or posting
- recruiter or job-search workflows
- generic agency CRM features
- heavy web application scaffolding
- background worker systems without a clear need

The intended product is a `daily work-prep tool`, not a sales automation stack.

## Architecture Expectations

When making changes, preserve these boundaries unless there is a strong reason to change them:

- `Python CLI` is the primary interface.
- `SQLite` is the default local state store.
- `run-daily` is the main operating loop.
- Discovery and assessment providers should use structured inputs and outputs.
- Packet generation should stay finite and reviewable.
- Generic system behavior should not be tightly coupled to one consulting thesis or buyer type; encode those choices in configurable profiles and presets.

If you propose a larger architectural shift, document why the current model is no longer sufficient.

## Testing And Validation

At minimum, run:

```bash
python3 -B -m unittest discover -s tests -v
```

If you change:

- command names
- workspace config behavior
- scheduling behavior
- provider contracts
- README examples

then make sure the docs and tests still reflect the real interface.

## Editing Guidance

- Prefer small, validated changes.
- Preserve backward compatibility where reasonable for workspace config and command behavior.
- Keep prompts and schemas explicit.
- Favor explainability over magic.
- Keep output caps and quality thresholds visible in code.

## When In Doubt

Choose the simpler design that:

- keeps the tool local
- keeps the workflow reviewable
- improves lead quality
- avoids turning the project into a larger system than it needs to be
