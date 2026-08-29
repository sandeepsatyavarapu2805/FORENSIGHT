# ForenSight backend

Run commands from this directory with `uv run`.

After applying migrations, create an investigator interactively:

```text
uv run python -m app.cli create-investigator <username> "<display name>"
```

The command prompts for a password without echoing it, requires at least 12
characters, stores only an Argon2id hash, and refuses duplicate usernames.

## M3 upload configuration

`UPLOAD_STORAGE_PATH` selects the local/persistent source-file root and
`UPLOAD_MAX_BYTES` sets the maximum accepted source size. Uploaded forensic files
are never stored in PostgreSQL or Git. Production UFDR parsing remains disabled
until a genuine supported sample is available; see `docs/M3_IMPLEMENTATION.md`.
