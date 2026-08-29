from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import analysis, ask, auth, cases, evidence, findings, reports, sources

app = FastAPI(
    title="ForenSight AI API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(sources.router)
app.include_router(evidence.router)
app.include_router(analysis.router)
app.include_router(ask.router)
app.include_router(findings.router)
app.include_router(reports.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
