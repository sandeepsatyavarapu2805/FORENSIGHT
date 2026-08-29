# ForenSight AI

ForenSight AI is a forensic investigation prototype with immutable normalized evidence,
case-scoped exploration and analysis, grounded question answering, investigator findings,
and deterministic printable reports.

Production UFDR artifact parsing is intentionally not claimed. The repository contains a
safe generic ZIP/XML container boundary and test/demo data only.

## Local verification

```text
cd backend
uv sync
uv run alembic upgrade head
uv run pytest
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

cd ../frontend
npm ci
npm run lint
npm run build
npm run dev
```

Copy each `.env.example` to `.env` for local development. Create an investigator with
`uv run python -m app.cli create-investigator <username> "<display name>"`.

The optional demo workflow is `uv run python -m app.cli seed-demo <username> "<display name>"`.
It creates explicitly labeled, fictional normalized evidence and must never be presented as
a real UFDR import.

## Render deployment

Create a Render Blueprint from `render.yaml`. Before the first deployment:

1. Set the backend `FRONTEND_ORIGIN` to the exact HTTPS URL of the static site.
2. Set frontend `VITE_API_BASE_URL` to the exact HTTPS URL of the API.
3. Keep `SESSION_COOKIE_SECURE=true` and `SESSION_COOKIE_SAMESITE=none` for the
   cross-origin frontend/API deployment.
4. Configure `AI_PROVIDER`, `AI_MODEL`, and `AI_API_KEY` only if external grounded answers
   are wanted. With `AI_PROVIDER=disabled`, deterministic evidence retrieval still works.
5. Deploy the database and API; the API start command applies Alembic migrations before
   starting. Confirm `/health` returns `{"status":"ok"}`.

The Blueprint includes a persistent disk for uploaded evidence. Render disk-backed services
may require a paid plan; do not deploy forensic uploads to ephemeral storage.

Relevant backend variables are documented in `backend/.env.example`. Secrets belong only in
Render environment settings and must never be added to the frontend.
