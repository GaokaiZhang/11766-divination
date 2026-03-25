"""
FastAPI backend for the divination companion.

Start from the 11766-divination/ directory with:
    uvicorn backend.app:app --reload
"""
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from .divination import SYSTEMS, UserBirthInfo
from .divination.base import DivinationResult
from .llm.client import DivinationLLM
from .user.profile import ProfileStore

app = FastAPI(title="Divination Companion")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend from /
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")

store = ProfileStore()
llm = DivinationLLM()  # reads OPENAI_API_KEY from env


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class StartRequest(BaseModel):
    user_id: str
    name: str
    birth_date: Optional[str] = None   # YYYY-MM-DD
    birth_time: Optional[str] = None   # HH:MM
    birth_location: Optional[str] = None
    question: Optional[str] = None
    system: str = "tarot"              # "tarot" | "bazi" | "iching"


class ChatRequest(BaseModel):
    user_id: str
    system: str
    result_raw: dict                   # DivinationResult.raw — sent back from client
    symbols: list[str] = []            # Key symbols for RAG query (sent from /start)
    reading_summary: str = ""          # Reading summary for context
    messages: list[dict]               # full conversation history so far


class EndSessionRequest(BaseModel):
    user_id: str
    messages: list[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/start")
def start_reading(req: StartRequest):
    if req.system not in SYSTEMS:
        raise HTTPException(400, f"Unknown system '{req.system}'. Choose from: {list(SYSTEMS)}")

    user_info = UserBirthInfo(
        name=req.name,
        birth_date=req.birth_date,
        birth_time=req.birth_time,
        birth_location=req.birth_location,
    )

    # Persist / update user profile
    profile = store.get_or_create(req.user_id, req.name)
    for attr in ("birth_date", "birth_time", "birth_location"):
        val = getattr(req, attr)
        if val:
            setattr(profile, attr, val)
    store.update(profile)

    system_obj = SYSTEMS[req.system]

    # Check for missing required info
    missing = user_info.missing_for(system_obj)
    if missing:
        question = system_obj.clarification_question(missing)
        return {"needs_clarification": True, "question": question}

    # Compute the reading
    result = system_obj.compute(user_info)

    # First LLM response
    user_msg = req.question or "Please give me a reading."
    messages = [{"role": "user", "content": user_msg}]
    reply = llm.chat(messages, result, profile)

    # Persist reading
    store.save_reading(req.user_id, req.system, result.raw, messages)

    return {
        "needs_clarification": False,
        "reading_summary": result.summary,
        "reading_raw": result.raw,
        "symbols": result.symbols,        # send symbols so /chat can use them
        "initial_question": user_msg,      # send so frontend can reconstruct history
        "reply": reply,
    }


@app.post("/chat")
def chat(req: ChatRequest):
    if req.system not in SYSTEMS:
        raise HTTPException(400, f"Unknown system '{req.system}'")

    profile = store.get_or_create(req.user_id, req.user_id)

    # Reconstruct DivinationResult from what the client stored
    result = DivinationResult(
        system=req.system,
        raw=req.result_raw,
        summary=req.reading_summary,
        symbols=req.symbols,
    )

    reply = llm.chat(req.messages, result, profile)
    return {"reply": reply}


@app.post("/end-session")
def end_session(req: EndSessionRequest):
    """Extract themes and persist them. Also save final conversation."""
    themes = llm.extract_themes(req.messages)
    for theme in themes:
        store.add_theme(req.user_id, theme)
    return {"extracted_themes": themes}
