import httpx
import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def clear_messages():
    server.messages.clear()


def test_index_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Group Chat Simulator" in response.text


def test_health_when_ollama_up(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "gemma4:e2b"}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ollama": "up",
        "models": ["gemma4:e2b"],
    }


def test_health_when_ollama_down(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "ollama": "down", "models": []}


def test_personas_are_listed_without_prompt_details():
    response = client.get("/api/personas")
    assert response.status_code == 200
    personas = response.json()
    assert [p["id"] for p in personas] == ["cantaretul", "eliade", "smecherasul"]
    for persona in personas:
        assert set(persona) == {"id", "name", "emoji"}


def test_messages_start_empty():
    response = client.get("/api/messages")
    assert response.status_code == 200
    assert response.json() == []


def test_message_without_mention_gets_replies_from_all_personas(monkeypatch):
    calls = []

    async def fake_ask_ollama(persona, history):
        calls.append((persona["id"], [m["author"] for m in history]))
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post("/api/messages", json={"text": "salut tuturor"})
    assert response.status_code == 201
    replies = response.json()
    assert [r["author"] for r in replies] == ["cantaretul", "eliade", "smecherasul"]
    assert replies[0]["text"] == "replică de la cantaretul"
    assert all("timestamp" in r for r in replies)

    # fiecare personaj vede în istoric replicile celor care au răspuns înaintea lui
    assert [history for _, history in calls] == [
        ["user"],
        ["user", "cantaretul"],
        ["user", "cantaretul", "eliade"],
    ]

    messages = client.get("/api/messages").json()
    assert [m["author"] for m in messages] == [
        "user",
        "cantaretul",
        "eliade",
        "smecherasul",
    ]
    assert messages[0]["text"] == "salut tuturor"


def test_mentioned_persona_is_the_only_one_replying(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return "sacrul se ascunde în profan"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post("/api/messages", json={"text": "@eliade ce părere ai?"})
    assert response.status_code == 201
    assert [r["author"] for r in response.json()] == ["eliade"]

    messages = client.get("/api/messages").json()
    assert [m["author"] for m in messages] == ["user", "eliade"]


def test_mentions_match_display_names_ignoring_diacritics(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post(
        "/api/messages",
        json={"text": "@Șmecherașul și @Cantaretul, voi ce ziceți?"},
    )
    assert [r["author"] for r in response.json()] == ["cantaretul", "smecherasul"]


def test_mention_by_name_word_matches_persona(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return "hermeneutică"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post("/api/messages", json={"text": "@Mircea, tu ce crezi?"})
    assert [r["author"] for r in response.json()] == ["eliade"]


def test_unknown_mention_counts_as_no_mention(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post("/api/messages", json={"text": "@necunoscut salut"})
    assert [r["author"] for r in response.json()] == [
        "cantaretul",
        "eliade",
        "smecherasul",
    ]


def test_ask_ollama_builds_chat_request(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "răspunsul metaforic"}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)

    persona = server.PERSONAS["cantaretul"]
    history = [
        {"author": "user", "text": "salut", "timestamp": "2026-08-10T12:00:00"},
        {"author": "cantaretul", "text": "hop și-așa", "timestamp": "2026-08-10T12:00:05"},
        {"author": "user", "text": "ce mai faci?", "timestamp": "2026-08-10T12:01:00"},
    ]
    import asyncio

    reply = asyncio.run(server.ask_ollama(persona, history))

    assert reply == "răspunsul metaforic"
    assert captured["url"] == f"{server.OLLAMA_URL}/api/chat"
    payload = captured["payload"]
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": persona["temperature"]}
    assert payload["messages"] == [
        {"role": "system", "content": persona["system_prompt"]},
        {"role": "user", "content": "salut"},
        {"role": "assistant", "content": "hop și-așa"},
        {"role": "user", "content": "ce mai faci?"},
    ]
