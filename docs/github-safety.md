# GitHub Safety

This repository is public. Every commit must keep it portfolio-safe.

## Never Commit

- Proprietary or company-internal documents of any kind
- Customer documents, customer data, or customer identifiers
- Internal screenshots (UIs, dashboards, chat logs, ticketing systems, internal tools)
- Real names, emails, employee IDs, account IDs, or other internal identifiers
- Secrets: API keys, tokens, OAuth credentials, database passwords, signing keys, certificates
- Real values in `.env`, configuration files, or sample notebooks
- Logs, traces, or debug output produced from real documents
- OCR output, extracted text, processed chunks, embeddings, or vector index files derived from private documents
- User uploads or anything copied out of `uploads/`
- Backups, exports, or dumps from real systems

## Allowed Sample Data

Only the following may live under `data/sample_data/`:

- Fully synthetic documents authored for this project
- Fictional scenarios (made-up companies, people, products)
- Documents that have been fully redacted such that no real identifier, content, or context remains

If in doubt, do not commit it.

## Keeping the Repo Safe for Public Portfolio Use

- Treat every file as if it will be indexed and read by strangers — because it will be.
- Keep `.gitignore` strict and review it before adding new file types.
- Verify `git status` before every commit; never use blanket `git add .` without reviewing the staged set.
- Never disable hooks or push checks to bypass safety rules.
- If a private file is accidentally staged, unstage it and remove it from disk before continuing.
- If a private file is accidentally committed, treat the commit as compromised: rotate any exposed secrets immediately and rewrite history before pushing.

## Secret Handling

- Real secrets live only in a local `.env` file, which is git-ignored.
- `.env.example` contains placeholder names with empty or non-sensitive default values only.
- Do not hardcode secrets in source files, tests, fixtures, notebooks, or Docker Compose files.
- Do not paste secrets into commit messages, PR descriptions, or issue comments.

## Environment and Config Rules

- All configuration is read from environment variables, sourced locally from `.env`.
- Defaults committed to the repository must be safe to publish (e.g., `localhost` hosts, placeholder usernames, local model identifiers).
- Do not commit `docker-compose.override.yml`, local IDE config with credentials, or machine-specific paths.

## Artifact, Log, and Output Handling

- All ingestion outputs (parsed text, OCR results, chunks, embeddings, vector indexes) are derived artifacts and must never be committed.
- Logs from local runs stay local; they are git-ignored.
- Local databases (`pgdata/`, `*.sqlite`, `*.db`) are git-ignored and must never be committed.
- If a sample run produces useful demonstration output, recreate it from synthetic inputs rather than committing the cached artifact.
