import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma4:e2b"

PERSONAS = {
    p["id"]: p
    for p in json.loads(
        (Path(__file__).parent / "personas.json").read_text(encoding="utf-8")
    )["personas"]
}

# Istoricul conversației, în memorie: {author, text, timestamp}
messages: list[dict] = []

app = FastAPI(title="Group Chat Simulator")


class MessageIn(BaseModel):
    text: str


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def mentioned_personas(text: str) -> list[dict]:
    """Personajele menționate cu @ în text, în ordinea din personas.json.

    O mențiune se potrivește după id sau după oricare cuvânt din nume,
    ignorând diacriticele și majusculele. Regulă provizorie (vezi PLAN.md).
    """
    tokens = {_normalize(t) for t in re.findall(r"@(\w+)", text)}
    return [
        p
        for p in PERSONAS.values()
        if tokens & ({p["id"]} | set(_normalize(p["name"]).split()))
    ]


async def ask_ollama(persona: dict, history: list[dict]) -> str:
    chat_messages = [{"role": "system", "content": persona["system_prompt"]}]
    for message in history:
        role = "assistant" if message["author"] == persona["id"] else "user"
        chat_messages.append({"role": role, "content": message["text"]})

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": chat_messages,
                "stream": False,
                "options": {"temperature": persona["temperature"]},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


@app.get("/api/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
        return {"status": "ok", "ollama": "up", "models": models}
    except httpx.HTTPError:
        return {"status": "degraded", "ollama": "down", "models": []}


@app.get("/api/personas")
async def get_personas():
    return [
        {"id": p["id"], "name": p["name"], "emoji": p["emoji"]}
        for p in PERSONAS.values()
    ]


@app.get("/api/messages")
async def get_messages():
    return messages


@app.post("/api/messages", status_code=201)
async def post_message(message: MessageIn):
    messages.append(
        {
            "author": "user",
            "text": message.text,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    )
    respondents = mentioned_personas(message.text) or list(PERSONAS.values())
    replies = []
    for persona in respondents:
        reply_text = await ask_ollama(persona, messages)
        reply = {
            "author": persona["id"],
            "text": reply_text,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        messages.append(reply)
        replies.append(reply)
    return replies


app.mount("/", StaticFiles(directory="static", html=True), name="static")
