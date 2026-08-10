import json
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
    persona = PERSONAS["cantaretul"]
    reply_text = await ask_ollama(persona, messages)
    reply = {
        "author": persona["id"],
        "text": reply_text,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    messages.append(reply)
    return reply


app.mount("/", StaticFiles(directory="static", html=True), name="static")
