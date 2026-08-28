# ForenSight backend

Run commands from this directory with `uv run`.

After applying migrations, create an investigator interactively:

```text
uv run python -m app.cli create-investigator <username> "<display name>"
```

The command prompts for a password without echoing it, requires at least 12
characters, stores only an Argon2id hash, and refuses duplicate usernames.
