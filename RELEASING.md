# Releasing LeadOps

## Before Publishing

1. Run tests:

```bash
python3 -B -m unittest discover -s tests -v
```

2. Review repo-local files:

- `README.md`
- `LICENSE`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `pyproject.toml`
- `.gitignore`

3. Confirm no secrets are in the repo:

- no API keys
- no SMTP passwords
- no private workspace data

4. Confirm the public examples are generic:

- no personal absolute paths in docs
- no private workspace references

## Initial GitHub Push

```bash
git init -b main
git add .
git commit -m "Initial setup"
git remote add origin git@github.com:<your-user-or-org>/leadops.git
git push -u origin main
```

## First Tagged Release

```bash
git tag v0.1.0
git push origin v0.1.0
```
