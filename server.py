import asyncio
import json
import logging
import os
import random
import re
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma4:e2b"
CONVERSATIONS_DIR = Path(__file__).parent / "conversations"

# Intervalul (aleator) dintre postările automate ale personajelor.
# Default-ul „de producție" e 2–8 minute; în dezvoltare setează ex. 10/30.
AUTO_POST_MIN_SECONDS = float(os.environ.get("AUTO_POST_MIN_SECONDS", "120"))
AUTO_POST_MAX_SECONDS = float(os.environ.get("AUTO_POST_MAX_SECONDS", "480"))

# Titlul dat manual unei conversații; peste atât, tăiem.
MAX_TITLE_LENGTH = 80

_personas_config = json.loads(
    (Path(__file__).parent / "personas.json").read_text(encoding="utf-8")
)
PERSONAS = {p["id"]: p for p in _personas_config["personas"]}
# Instrucțiuni comune, adăugate la promptul fiecărui personaj; {participants}
# se înlocuiește cu lista celorlalți, ca să știe pe cine pot chema cu @.
SHARED_SYSTEM_PROMPT = _personas_config["shared_system_prompt"]

# Conversațiile, în memorie: {id: {id, created_at, messages: [{author, text, timestamp}]}}
# Fiecare conversație se oglindește într-un fișier JSON din CONVERSATIONS_DIR.
conversations: dict[str, dict] = {}

# Conversația „activă" — cea mai recent folosită (creată, citită sau scrisă);
# doar în ea postează personajele automat.
active_conversation_id: str | None = None

# Cine „scrie" acum, cât se așteaptă Ollama: {conversation_id: persona_id}
typing: dict[str, str] = {}


async def auto_post_loop() -> None:
    while True:
        await asyncio.sleep(auto_post_delay())
        try:
            await auto_post_once()
        except Exception:
            # Ollama căzut etc. — nu omorâm task-ul, reîncercăm la următorul interval
            logging.getLogger("uvicorn.error").exception("Postarea automată a eșuat")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(auto_post_loop())
    yield
    task.cancel()


app = FastAPI(title="Group Chat Simulator", lifespan=lifespan)


class MessageIn(BaseModel):
    text: str


class ConversationPatch(BaseModel):
    title: str


def new_conversation() -> dict:
    global active_conversation_id
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
    active_conversation_id = conversation_id
    return conversation


def newest_conversation_id() -> str:
    return max(conversations.values(), key=lambda c: (c["created_at"], c["id"]))["id"]


def load_conversations() -> None:
    """Încarcă toate conversațiile de pe disc; dacă nu există niciuna, începe una nouă.

    Conversațiile goale nu au încă fișier (se scrie la primul mesaj), deci un
    server proaspăt nu lasă nimic pe disc până nu se scrie ceva în chat.
    """
    global active_conversation_id
    conversations.clear()
    typing.clear()
    if CONVERSATIONS_DIR.is_dir():
        for path in sorted(CONVERSATIONS_DIR.glob("*.json")):
            conversation = json.loads(path.read_text(encoding="utf-8"))
            conversations[conversation["id"]] = conversation
    if not conversations:
        new_conversation()
    active_conversation_id = newest_conversation_id()


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
        # None = neredenumită; frontend-ul afișează atunci data creării
        "title": conversation.get("title"),
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


def system_prompt_for(persona: dict) -> str:
    """Promptul propriu al personajului + instrucțiunile comune, cu lista
    celorlalți participanți și handle-urile lor de @."""
    participants = ", ".join(
        f"{p['name']} (@{p['id']})"
        for p in PERSONAS.values()
        if p["id"] != persona["id"]
    )
    return (
        f"{persona['system_prompt']}\n\n"
        f"{SHARED_SYSTEM_PROMPT.format(participants=participants)}"
    )


async def ask_ollama(persona: dict, history: list[dict]) -> str:
    """Cere o replică de la Ollama, în numele personajului dat.

    Mesajele celorlalți (rol „user") sunt prefixate cu numele autorului,
    altfel modelul nu are cum să știe cine ce a spus și atribuie greșit
    replicile (verificat empiric în experiments/).
    """
    chat_messages = [{"role": "system", "content": system_prompt_for(persona)}]
    for message in history:
        if message["author"] == persona["id"]:
            chat_messages.append({"role": "assistant", "content": message["text"]})
        else:
            author = PERSONAS.get(message["author"])
            name = author["name"] if author else "Utilizatorul"
            chat_messages.append(
                {"role": "user", "content": f"[{name}]: {message['text']}"}
            )

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


def auto_post_delay() -> float:
    return random.uniform(AUTO_POST_MIN_SECONDS, AUTO_POST_MAX_SECONDS)


async def auto_post_once() -> dict | None:
    """O postare automată în conversația activă: un personaj tras la sorți
    (aceleași ponderi 80/20, deci chemările nestinse contează) spune ceva
    din proprie inițiativă, pe baza istoricului."""
    conversation = conversations.get(active_conversation_id)
    if conversation is None:
        return None
    messages = conversation["messages"]
    persona = choose_respondent(messages)
    typing[conversation["id"]] = persona["id"]
    try:
        reply_text = await ask_ollama(persona, messages)
    finally:
        typing.pop(conversation["id"], None)
    reply = {
        "author": persona["id"],
        "text": reply_text,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    messages.append(reply)
    save_conversation(conversation)
    return reply


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


@app.patch("/api/conversations/{conversation_id}")
async def patch_conversation(conversation_id: str, patch: ConversationPatch):
    """Redenumește o conversație; un titlu gol o readuce la eticheta cu data."""
    conversation = get_conversation_or_404(conversation_id)
    title = patch.title.strip()[:MAX_TITLE_LENGTH]
    if title:
        conversation["title"] = title
    else:
        conversation.pop("title", None)
    save_conversation(conversation)
    return conversation_summary(conversation)


@app.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str):
    """Șterge conversația, din memorie și de pe disc.

    Aplicația are mereu cel puțin o conversație: dacă tocmai am șters-o pe
    ultima, pornim una nouă, goală.
    """
    global active_conversation_id
    get_conversation_or_404(conversation_id)
    del conversations[conversation_id]
    (CONVERSATIONS_DIR / f"{conversation_id}.json").unlink(missing_ok=True)
    typing.pop(conversation_id, None)
    if not conversations:
        new_conversation()
    elif active_conversation_id == conversation_id:
        active_conversation_id = newest_conversation_id()


@app.get("/api/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    global active_conversation_id
    conversation = get_conversation_or_404(conversation_id)
    active_conversation_id = conversation_id
    return {
        "messages": conversation["messages"],
        "typing": typing.get(conversation_id),
    }


@app.post("/api/conversations/{conversation_id}/messages", status_code=201)
async def post_message(conversation_id: str, message: MessageIn):
    global active_conversation_id
    conversation = get_conversation_or_404(conversation_id)
    active_conversation_id = conversation_id
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
    typing[conversation_id] = persona["id"]
    try:
        reply_text = await ask_ollama(persona, messages)
    finally:
        typing.pop(conversation_id, None)
    reply = {
        "author": persona["id"],
        "text": reply_text,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    messages.append(reply)
    save_conversation(conversation)
    return [reply]


load_conversations()

app.mount("/", StaticFiles(directory="static", html=True), name="static")
