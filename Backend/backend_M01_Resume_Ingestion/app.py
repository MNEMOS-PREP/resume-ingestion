from __future__ import annotations

import logging
from contextlib import asynccontextmanager

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

@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "module": "M01"}
