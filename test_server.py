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


def test_messages_start_empty():
    response = client.get("/api/messages")
    assert response.status_code == 200
    assert response.json() == []


def test_post_message_gets_reply_from_cantaretul(monkeypatch):
    async def fake_ask_ollama(persona, history):
        assert persona["id"] == "cantaretul"
        assert history[-1]["author"] == "user"
        assert history[-1]["text"] == "salut"
        return "Viața e ca o doină cântată la nedeie, măi frate!"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    response = client.post("/api/messages", json={"text": "salut"})
    assert response.status_code == 201
    reply = response.json()
    assert reply["author"] == "cantaretul"
    assert reply["text"] == "Viața e ca o doină cântată la nedeie, măi frate!"
    assert "timestamp" in reply

    messages = client.get("/api/messages").json()
    assert [m["author"] for m in messages] == ["user", "cantaretul"]
    assert messages[0]["text"] == "salut"
    assert all("timestamp" in m for m in messages)


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
