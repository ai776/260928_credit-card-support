from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import ChatRequest, ChatResponse
from app.service import Desk

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

app = FastAPI(title="アオカード会員サポート", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
desk = Desk()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {
        "jev": bool(os.environ.get("TYPESAFE_API_KEY")),
        "generation": bool(os.environ.get("GENERATION_API_KEY")),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    return desk.reply(body.message, body.session_id)
