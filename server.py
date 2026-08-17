import json
import random
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma4:e2b"
CONVERSATIONS_DIR = Path(__file__).parent / "conversations"

PERSONAS = {
    p["id"]: p
    for p in json.loads(
        (Path(__file__).parent / "personas.json").read_text(encoding="utf-8")
    )["personas"]
}

# Conversațiile, în memorie: {id: {id, created_at, messages: [{author, text, timestamp}]}}
# Fiecare conversație se oglindește într-un fișier JSON din CONVERSATIONS_DIR.
conversations: dict[str, dict] = {}

app = FastAPI(title="Group Chat Simulator")


class MessageIn(BaseModel):
    text: str


def new_conversation() -> dict:
    now = datetime.now()
    conversation_id = now.strftime("%Y-%m-%dT%H-%M-%S")
    suffix = 2
    while conversation_id in conversations:
        conversation_id = f"{now.strftime('%Y-%m-%dT%H-%M-%S')}-{suffix}"
        suffix += 1
    conversation = {
        "id": conversation_id,
        "created_at": now.isoformat(timespec="seconds"),
        "messages": [],
    }
    conversations[conversation_id] = conversation
    return conversation


def load_conversations() -> None:
    """Încarcă toate conversațiile de pe disc; dacă nu există niciuna, începe una nouă.

    Conversațiile goale nu au încă fișier (se scrie la primul mesaj), deci un
    server proaspăt nu lasă nimic pe disc până nu se scrie ceva în chat.
    """
    conversations.clear()
    if CONVERSATIONS_DIR.is_dir():
        for path in sorted(CONVERSATIONS_DIR.glob("*.json")):
            conversation = json.loads(path.read_text(encoding="utf-8"))
            conversations[conversation["id"]] = conversation
    if not conversations:
        new_conversation()


def save_conversation(conversation: dict) -> None:
    CONVERSATIONS_DIR.mkdir(exist_ok=True)
    path = CONVERSATIONS_DIR / f"{conversation['id']}.json"
    path.write_text(
        json.dumps(conversation, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def conversation_summary(conversation: dict) -> dict:
    return {
        "id": conversation["id"],
        "created_at": conversation["created_at"],
        "message_count": len(conversation["messages"]),
    }


def get_conversation_or_404(conversation_id: str) -> dict:
    conversation = conversations.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversația nu există")
    return conversation


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def mentioned_personas(text: str) -> list[dict]:
    """Personajele menționate cu @ în text, în ordinea din personas.json.

    O mențiune se potrivește după id sau după oricare cuvânt din nume,
    ignorând diacriticele și majusculele.
    """
    tokens = {_normalize(t) for t in re.findall(r"@(\w+)", text)}
    return [
        p
        for p in PERSONAS.values()
        if tokens & ({p["id"]} | set(_normalize(p["name"]).split()))
    ]


def pending_mentions(messages: list[dict]) -> set[str]:
    """Id-urile personajelor „chemate": menționate cu @ într-un mesaj oarecare
    (al utilizatorului sau al altui personaj) și care n-au mai postat de la
    mențiune — postarea stinge mențiunea. Auto-mențiunile nu contează.
    """
    pending: set[str] = set()
    for message in messages:
        pending.discard(message["author"])
        pending |= {
            p["id"]
            for p in mentioned_personas(message["text"])
            if p["id"] != message["author"]
        }
    return pending


def respondent_weights(messages: list[dict]) -> dict[str, float]:
    """Ponderile tragerii la sorți pentru cine răspunde mesajului utilizatorului.

    Personajele chemate (vezi pending_mentions) împart egal 80% din șanse,
    celelalte restul de 20%. Dacă una dintre grupe e goală (niciun personaj
    chemat sau toate chemate), șansele sunt egale.
    """
    mentioned = pending_mentions(messages)
    unmentioned = [pid for pid in PERSONAS if pid not in mentioned]
    if not mentioned or not unmentioned:
        return {pid: 1 / len(PERSONAS) for pid in PERSONAS}
    return {
        pid: 0.8 / len(mentioned) if pid in mentioned else 0.2 / len(unmentioned)
        for pid in PERSONAS
    }


def choose_respondent(messages: list[dict]) -> dict:
    """Alege un singur personaj care să răspundă, prin tragere la sorți ponderată."""
    weights = respondent_weights(messages)
    (winner,) = random.choices(list(weights), weights=list(weights.values()))
    return PERSONAS[winner]


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
        {"id": p["id"], "name": p["name"], "emoji": p["emoji"], "color": p["color"]}
        for p in PERSONAS.values()
    ]


@app.get("/api/conversations")
async def get_conversations():
    return [
        conversation_summary(c)
        for c in sorted(
            conversations.values(),
            key=lambda c: (c["created_at"], c["id"]),
            reverse=True,
        )
    ]


@app.post("/api/conversations", status_code=201)
async def post_conversation():
    return conversation_summary(new_conversation())


@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    return get_conversation_or_404(conversation_id)["messages"]


@app.post("/api/conversations/{conversation_id}/messages", status_code=201)
async def post_message(conversation_id: str, message: MessageIn):
    conversation = get_conversation_or_404(conversation_id)
    messages = conversation["messages"]
    messages.append(
        {
            "author": "user",
            "text": message.text,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_conversation(conversation)
    persona = choose_respondent(messages)
    reply = {
        "author": persona["id"],
        "text": await ask_ollama(persona, messages),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    messages.append(reply)
    save_conversation(conversation)
    return [reply]


load_conversations()

app.mount("/", StaticFiles(directory="static", html=True), name="static")
