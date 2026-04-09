# Contributing

LeadOps is a small local CLI for precision lead curation. Contributions should keep the tool narrow, inspectable, and human-reviewed.

## Principles

- Optimize for precision, not volume.
- Do not turn the project into an autonomous outreach agent.
- Keep new features inspectable and easy to disable.
- Prefer small, validated changes over broad framework additions.

## Development

Create a virtual environment and install editable dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run tests:

```bash
python3 -B -m unittest discover -s tests -v
```

## Pull Requests

- Keep PRs focused.
- Update tests when behavior changes.
- Update `README.md` when commands, config, or workflow change.
- Do not add secrets, personal workspace paths, or private customer data.

## Scope Guardrails

Changes are less likely to be accepted if they:

- add auto-send or autonomous outreach behavior
- broaden the tool into a CRM
- add a heavy web app or service architecture without a strong reason
- optimize for raw lead count instead of fit quality
