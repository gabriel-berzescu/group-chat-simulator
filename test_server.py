import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)

ALL_PERSONA_IDS = list(server.PERSONAS)


@pytest.fixture(autouse=True)
def isolated_conversations(tmp_path, monkeypatch):
    """Fiecare test pornește cu un director de conversații gol, în tmp_path."""
    monkeypatch.setattr(server, "CONVERSATIONS_DIR", tmp_path)
    server.load_conversations()


def newest_conversation_id():
    return client.get("/api/conversations").json()[0]["id"]


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
    assert [p["id"] for p in personas] == ALL_PERSONA_IDS
    for persona in personas:
        assert set(persona) == {"id", "name", "emoji", "color"}


# --- Conversații (Faza 2b) ---


def test_a_fresh_server_starts_with_one_empty_conversation():
    response = client.get("/api/conversations")
    assert response.status_code == 200
    conversations = response.json()
    assert len(conversations) == 1
    (conversation,) = conversations
    assert set(conversation) == {"id", "created_at", "message_count"}
    assert conversation["message_count"] == 0


def test_empty_startup_conversation_is_not_written_to_disk(tmp_path):
    assert list(tmp_path.iterdir()) == []


def test_new_conversation_is_created_and_listed_first():
    existing_id = newest_conversation_id()

    response = client.post("/api/conversations")
    assert response.status_code == 201
    created = response.json()
    assert created["message_count"] == 0

    ids = [c["id"] for c in client.get("/api/conversations").json()]
    assert ids[0] == created["id"]
    assert existing_id in ids
    assert len(set(ids)) == 2


def test_conversations_are_loaded_from_disk(tmp_path):
    saved = {
        "id": "2026-08-10T09-00-00",
        "created_at": "2026-08-10T09:00:00",
        "messages": [
            {
                "author": "user",
                "text": "bună dimineața",
                "timestamp": "2026-08-10T09:00:00",
            }
        ],
    }
    (tmp_path / "2026-08-10T09-00-00.json").write_text(
        json.dumps(saved, ensure_ascii=False), encoding="utf-8"
    )

    server.load_conversations()

    conversations = client.get("/api/conversations").json()
    assert [c["id"] for c in conversations] == ["2026-08-10T09-00-00"]
    assert conversations[0]["message_count"] == 1

    messages = client.get("/api/conversations/2026-08-10T09-00-00/messages").json()
    assert [m["text"] for m in messages] == ["bună dimineața"]


def test_posted_messages_are_saved_to_the_conversation_file(tmp_path, monkeypatch):
    async def fake_ask_ollama(persona, history):
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()

    client.post(f"/api/conversations/{conversation_id}/messages", json={"text": "salut"})

    saved = json.loads(
        (tmp_path / f"{conversation_id}.json").read_text(encoding="utf-8")
    )
    assert saved["id"] == conversation_id
    assert "created_at" in saved
    assert [m["author"] for m in saved["messages"]] == ["user", *ALL_PERSONA_IDS]
    assert saved["messages"][0]["text"] == "salut"


def test_conversation_survives_a_restart(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return "rămân aici și după restart"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()
    client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "@eliade salut"}
    )

    server.load_conversations()  # simulează repornirea serverului

    assert [c["id"] for c in client.get("/api/conversations").json()] == [conversation_id]
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [m["author"] for m in messages] == ["user", "eliade"]


def test_messages_are_scoped_to_their_conversation(monkeypatch):
    histories = []

    async def fake_ask_ollama(persona, history):
        histories.append([m["text"] for m in history])
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    first_id = newest_conversation_id()
    client.post(f"/api/conversations/{first_id}/messages", json={"text": "@eliade unu"})

    second_id = client.post("/api/conversations").json()["id"]
    client.post(f"/api/conversations/{second_id}/messages", json={"text": "@eliade doi"})

    first = client.get(f"/api/conversations/{first_id}/messages").json()
    second = client.get(f"/api/conversations/{second_id}/messages").json()
    assert [m["author"] for m in first] == ["user", "eliade"]
    assert [m["author"] for m in second] == ["user", "eliade"]
    assert first[0]["text"] == "@eliade unu"
    assert second[0]["text"] == "@eliade doi"

    # istoricul trimis la Ollama e doar cel al conversației respective
    assert histories == [["@eliade unu"], ["@eliade doi"]]


def test_unknown_conversation_returns_404():
    assert client.get("/api/conversations/inexistent/messages").status_code == 404
    response = client.post(
        "/api/conversations/inexistent/messages", json={"text": "salut"}
    )
    assert response.status_code == 404


# --- Mesaje și personaje ---


def test_messages_start_empty():
    response = client.get(f"/api/conversations/{newest_conversation_id()}/messages")
    assert response.status_code == 200
    assert response.json() == []


def test_message_without_mention_gets_replies_from_all_personas(monkeypatch):
    calls = []

    async def fake_ask_ollama(persona, history):
        calls.append((persona["id"], [m["author"] for m in history]))
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()

    response = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "salut tuturor"}
    )
    assert response.status_code == 201
    replies = response.json()
    assert [r["author"] for r in replies] == ALL_PERSONA_IDS
    assert replies[0]["text"] == f"replică de la {ALL_PERSONA_IDS[0]}"
    assert all("timestamp" in r for r in replies)

    # fiecare personaj vede în istoric replicile celor care au răspuns înaintea lui
    assert [history for _, history in calls] == [
        ["user", *ALL_PERSONA_IDS[:i]] for i in range(len(ALL_PERSONA_IDS))
    ]

    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [m["author"] for m in messages] == ["user", *ALL_PERSONA_IDS]
    assert messages[0]["text"] == "salut tuturor"


def test_mentioned_persona_is_the_only_one_replying(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return "sacrul se ascunde în profan"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()

    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"text": "@eliade ce părere ai?"},
    )
    assert response.status_code == 201
    assert [r["author"] for r in response.json()] == ["eliade"]

    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()
    assert [m["author"] for m in messages] == ["user", "eliade"]


def test_mentions_match_display_names_ignoring_diacritics(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post(
        f"/api/conversations/{newest_conversation_id()}/messages",
        json={"text": "@Șmecherașul și @Cantaretul, voi ce ziceți?"},
    )
    assert [r["author"] for r in response.json()] == ["cantaretul", "smecherasul"]


def test_mention_by_name_word_matches_persona(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return "hermeneutică"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post(
        f"/api/conversations/{newest_conversation_id()}/messages",
        json={"text": "@Mircea, tu ce crezi?"},
    )
    assert [r["author"] for r in response.json()] == ["eliade"]


def test_unknown_mention_counts_as_no_mention(monkeypatch):
    async def fake_ask_ollama(persona, history):
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post(
        f"/api/conversations/{newest_conversation_id()}/messages",
        json={"text": "@necunoscut salut"},
    )
    assert [r["author"] for r in response.json()] == ALL_PERSONA_IDS


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
