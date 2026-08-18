from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from ai_core.modules_meta import ModuleStatus, module_status
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, create_engine

from backend_M01_Resume_Ingestion.router import router

log = logging.getLogger("uvicorn.error")

DATABASE_URL = "sqlite:///dev_m01.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

@asynccontextmanager
async def lifespan(_app: FastAPI):
    SQLModel.metadata.create_all(engine)
    log.info("M01 database tables created.")
    yield

app = FastAPI(title="M01 — Resume Ingestion & Claim Extract", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/status", response_model=ModuleStatus, tags=["meta"])
def status() -> ModuleStatus:
    """What the PLATFORM registry says this module is.

    Deliberately not this module's own opinion of itself: the registry in
    Platform_Core is what the shell and the gateway read, and the two
    disagreeing is worth being able to see in one request.
    """
    return module_status("M01")


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "module": "M01"}
