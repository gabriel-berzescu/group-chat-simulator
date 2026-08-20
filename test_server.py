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


@pytest.fixture
def weighted_draw(monkeypatch):
    """Face tragerea la sorți deterministă: câștigă ponderea maximă (primul
    personaj, la egalitate). Întoarce lista tragerilor, ca testele să poată
    verifica ponderile folosite."""
    draws = []

    def fake_choices(population, weights):
        draws.append(dict(zip(population, weights)))
        return [max(zip(population, weights), key=lambda pair: pair[1])[0]]

    monkeypatch.setattr(server.random, "choices", fake_choices)
    return draws


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
    assert set(conversation) == {"id", "created_at", "title", "message_count"}
    assert conversation["title"] is None
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


def test_conversation_is_renamed_and_title_persists(tmp_path):
    conversation_id = newest_conversation_id()

    response = client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "  Bairam  "}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Bairam"

    assert client.get("/api/conversations").json()[0]["title"] == "Bairam"
    saved = json.loads((tmp_path / f"{conversation_id}.json").read_text(encoding="utf-8"))
    assert saved["title"] == "Bairam"


def test_long_title_is_capped():
    conversation_id = newest_conversation_id()
    response = client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "a" * 200}
    )
    assert response.json()["title"] == "a" * server.MAX_TITLE_LENGTH


def test_empty_title_restores_the_default_label():
    conversation_id = newest_conversation_id()
    client.patch(f"/api/conversations/{conversation_id}", json={"title": "Bairam"})

    response = client.patch(f"/api/conversations/{conversation_id}", json={"title": "   "})
    assert response.status_code == 200
    assert response.json()["title"] is None


def test_renaming_a_missing_conversation_is_404():
    response = client.patch("/api/conversations/nu-exista", json={"title": "x"})
    assert response.status_code == 404


def test_deleted_conversation_disappears_from_list_and_disk(tmp_path, monkeypatch, weighted_draw):
    async def fake_ask_ollama(persona, history):
        return "ceva"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    kept_id = newest_conversation_id()
    doomed_id = client.post("/api/conversations").json()["id"]
    client.post(f"/api/conversations/{doomed_id}/messages", json={"text": "salut"})
    assert (tmp_path / f"{doomed_id}.json").exists()

    response = client.delete(f"/api/conversations/{doomed_id}")
    assert response.status_code == 204

    assert [c["id"] for c in client.get("/api/conversations").json()] == [kept_id]
    assert not (tmp_path / f"{doomed_id}.json").exists()
    assert client.get(f"/api/conversations/{doomed_id}/messages").status_code == 404


def test_deleting_an_empty_conversation_without_a_file_works():
    doomed_id = client.post("/api/conversations").json()["id"]
    assert client.delete(f"/api/conversations/{doomed_id}").status_code == 204
    assert doomed_id not in [c["id"] for c in client.get("/api/conversations").json()]


def test_deleting_the_last_conversation_leaves_a_fresh_empty_one(monkeypatch, weighted_draw):
    async def fake_ask_ollama(persona, history):
        return "ceva"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    only_id = newest_conversation_id()
    client.post(f"/api/conversations/{only_id}/messages", json={"text": "salut"})

    assert client.delete(f"/api/conversations/{only_id}").status_code == 204

    # id-ul se derivă din secunda curentă, deci poate fi chiar același;
    # ce contează e că a rămas o conversație și că e goală
    conversations = client.get("/api/conversations").json()
    assert len(conversations) == 1
    assert conversations[0]["message_count"] == 0
    fresh_id = conversations[0]["id"]
    assert client.get(f"/api/conversations/{fresh_id}/messages").json()["messages"] == []


def test_deleting_the_active_conversation_moves_auto_posts_elsewhere():
    kept_id = newest_conversation_id()
    doomed_id = client.post("/api/conversations").json()["id"]
    assert server.active_conversation_id == doomed_id

    client.delete(f"/api/conversations/{doomed_id}")

    assert server.active_conversation_id == kept_id


def test_deleting_a_missing_conversation_is_404():
    assert client.delete("/api/conversations/nu-exista").status_code == 404


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

    messages = client.get("/api/conversations/2026-08-10T09-00-00/messages").json()[
        "messages"
    ]
    assert [m["text"] for m in messages] == ["bună dimineața"]


def test_posted_messages_are_saved_to_the_conversation_file(
    tmp_path, monkeypatch, weighted_draw
):
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
    assert [m["author"] for m in saved["messages"]] == ["user", ALL_PERSONA_IDS[0]]
    assert saved["messages"][0]["text"] == "salut"


def test_conversation_survives_a_restart(monkeypatch, weighted_draw):
    async def fake_ask_ollama(persona, history):
        return "rămân aici și după restart"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()
    client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "@eliade salut"}
    )

    server.load_conversations()  # simulează repornirea serverului

    assert [c["id"] for c in client.get("/api/conversations").json()] == [conversation_id]
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()[
        "messages"
    ]
    assert [m["author"] for m in messages] == ["user", "eliade"]


def test_messages_are_scoped_to_their_conversation(monkeypatch, weighted_draw):
    histories = []

    async def fake_ask_ollama(persona, history):
        histories.append([m["text"] for m in history])
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)

    first_id = newest_conversation_id()
    client.post(f"/api/conversations/{first_id}/messages", json={"text": "@eliade unu"})

    second_id = client.post("/api/conversations").json()["id"]
    client.post(f"/api/conversations/{second_id}/messages", json={"text": "@eliade doi"})

    first = client.get(f"/api/conversations/{first_id}/messages").json()["messages"]
    second = client.get(f"/api/conversations/{second_id}/messages").json()["messages"]
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


def test_messages_start_empty_and_nobody_is_typing():
    response = client.get(f"/api/conversations/{newest_conversation_id()}/messages")
    assert response.status_code == 200
    assert response.json() == {"messages": [], "typing": None}


# --- Tragerea la sorți a respondentului (regula 80/20) ---


def msg(author, text):
    return {"author": author, "text": text, "timestamp": "2026-08-17T12:00:00"}


def uniform_weights():
    return {pid: pytest.approx(1 / len(ALL_PERSONA_IDS)) for pid in ALL_PERSONA_IDS}


def test_weights_give_a_single_mentioned_persona_80_percent():
    weights = server.respondent_weights([msg("user", "@eliade ce părere ai?")])
    rest = {pid for pid in ALL_PERSONA_IDS if pid != "eliade"}
    assert weights["eliade"] == pytest.approx(0.8)
    assert all(weights[pid] == pytest.approx(0.2 / len(rest)) for pid in rest)
    assert sum(weights.values()) == pytest.approx(1)


def test_weights_split_the_80_percent_between_mentioned_personas():
    weights = server.respondent_weights([msg("user", "@eliade și @bunica, voi ce ziceți?")])
    rest = {pid for pid in ALL_PERSONA_IDS if pid not in {"eliade", "bunica"}}
    assert weights["eliade"] == weights["bunica"] == pytest.approx(0.4)
    assert all(weights[pid] == pytest.approx(0.2 / len(rest)) for pid in rest)


def test_weights_are_equal_without_mentions():
    assert server.respondent_weights([msg("user", "salut tuturor")]) == uniform_weights()


def test_weights_are_equal_when_everyone_is_mentioned():
    text = " ".join(f"@{pid}" for pid in ALL_PERSONA_IDS)
    assert server.respondent_weights([msg("user", text)]) == uniform_weights()


def test_unknown_mention_counts_as_no_mention():
    assert server.respondent_weights([msg("user", "@necunoscut salut")]) == uniform_weights()


def test_mentions_match_display_names_ignoring_diacritics():
    weights = server.respondent_weights(
        [msg("user", "@Șmecherașul și @Cantaretul, voi ce ziceți?")]
    )
    assert weights["cantaretul"] == weights["smecherasul"] == pytest.approx(0.4)


def test_mention_by_name_word_matches_persona():
    weights = server.respondent_weights([msg("user", "@Mircea, tu ce crezi?")])
    assert weights["eliade"] == pytest.approx(0.8)


def test_mention_stays_active_until_the_persona_speaks():
    weights = server.respondent_weights(
        [
            msg("user", "@eliade și @bunica, voi ce ziceți?"),
            msg("eliade", "sacrul se ascunde în profan"),
            msg("user", "interesant, mai spuneți"),
        ]
    )
    # bunica e încă „chemată"; mențiunea lui eliade s-a stins când a vorbit
    assert weights["bunica"] == pytest.approx(0.8)
    assert weights["eliade"] == pytest.approx(0.2 / (len(ALL_PERSONA_IDS) - 1))


def test_personas_can_mention_each_other():
    weights = server.respondent_weights(
        [
            msg("user", "salut tuturor"),
            msg("cantaretul", "asta să i-o spui lui @eliade, că el le știe"),
        ]
    )
    assert weights["eliade"] == pytest.approx(0.8)


def test_a_persona_mentioning_itself_is_not_favored():
    weights = server.respondent_weights(
        [msg("cantaretul", "eu, @cantaretul, așa zic mereu")]
    )
    assert weights == uniform_weights()


def test_choose_respondent_returns_a_known_persona():
    assert server.choose_respondent([msg("user", "salut")])["id"] in ALL_PERSONA_IDS


def test_message_gets_exactly_one_reply_drawn_with_the_weights(
    monkeypatch, weighted_draw
):
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
    assert [r["author"] for r in replies] == [ALL_PERSONA_IDS[0]]
    assert replies[0]["text"] == f"replică de la {ALL_PERSONA_IDS[0]}"
    assert "timestamp" in replies[0]

    # fără mențiuni, tragerea la sorți s-a făcut cu ponderi egale
    assert weighted_draw == [uniform_weights()]
    # respondentul vede în istoric mesajul utilizatorului
    assert calls == [(ALL_PERSONA_IDS[0], ["user"])]

    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()[
        "messages"
    ]
    assert [m["author"] for m in messages] == ["user", ALL_PERSONA_IDS[0]]
    assert messages[0]["text"] == "salut tuturor"


def test_mentioned_persona_wins_the_draw_with_80_percent(monkeypatch, weighted_draw):
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
    assert weighted_draw[0]["eliade"] == pytest.approx(0.8)

    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()[
        "messages"
    ]
    assert [m["author"] for m in messages] == ["user", "eliade"]


def test_unanswered_mention_is_favored_at_the_next_draw(monkeypatch, weighted_draw):
    async def fake_ask_ollama(persona, history):
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()

    # eliade și bunica sunt chemați; câștigă eliade (primul la egalitate de ponderi)
    response = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"text": "@eliade și @bunica, voi ce ziceți?"},
    )
    assert [r["author"] for r in response.json()] == ["eliade"]

    # bunica n-a apucat să răspundă, deci la următorul mesaj are singură cei 80%
    client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "mai ziceți ceva"}
    )
    assert weighted_draw[1]["bunica"] == pytest.approx(0.8)
    assert weighted_draw[1]["eliade"] == pytest.approx(0.2 / (len(ALL_PERSONA_IDS) - 1))


# --- Faza 3: chatul „viu" ---


def test_the_newest_conversation_is_active_after_startup():
    assert server.active_conversation_id == newest_conversation_id()


def test_creating_a_conversation_makes_it_active():
    created = client.post("/api/conversations").json()
    assert server.active_conversation_id == created["id"]


def test_viewing_a_conversation_makes_it_active():
    first_id = newest_conversation_id()
    client.post("/api/conversations")

    client.get(f"/api/conversations/{first_id}/messages")

    assert server.active_conversation_id == first_id


def test_typing_persona_is_exposed_while_waiting_for_ollama(monkeypatch, weighted_draw):
    seen = {}

    async def fake_ask_ollama(persona, history):
        seen["during"] = dict(server.typing)
        return "sacrul se ascunde în profan"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()

    client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "@eliade salut"}
    )

    # cât a durat apelul la Ollama, eliade era „typing"; după, nu mai e nimeni
    assert seen["during"] == {conversation_id: "eliade"}
    response = client.get(f"/api/conversations/{conversation_id}/messages")
    assert response.json()["typing"] is None


def test_auto_post_adds_a_reply_to_the_active_conversation(
    tmp_path, monkeypatch, weighted_draw
):
    async def fake_ask_ollama(persona, history):
        return f"monolog de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()

    reply = asyncio.run(server.auto_post_once())

    assert reply["author"] == ALL_PERSONA_IDS[0]  # ponderi egale → primul, determinist
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()[
        "messages"
    ]
    assert [m["author"] for m in messages] == [ALL_PERSONA_IDS[0]]
    saved = json.loads(
        (tmp_path / f"{conversation_id}.json").read_text(encoding="utf-8")
    )
    assert [m["author"] for m in saved["messages"]] == [ALL_PERSONA_IDS[0]]


def test_auto_post_favors_unanswered_mentions(monkeypatch, weighted_draw):
    async def fake_ask_ollama(persona, history):
        return f"replică de la {persona['id']}"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()
    client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"text": "@eliade și @bunica, voi ce ziceți?"},
    )

    # eliade a răspuns la mesaj; bunica e încă chemată, deci postarea automată o alege
    reply = asyncio.run(server.auto_post_once())

    assert reply["author"] == "bunica"


def test_auto_post_sets_the_typing_flag_while_generating(monkeypatch, weighted_draw):
    seen = {}

    async def fake_ask_ollama(persona, history):
        seen["during"] = dict(server.typing)
        return "vorbesc singur"

    monkeypatch.setattr(server, "ask_ollama", fake_ask_ollama)
    conversation_id = newest_conversation_id()

    asyncio.run(server.auto_post_once())

    assert seen["during"] == {conversation_id: ALL_PERSONA_IDS[0]}
    assert server.typing == {}


def test_auto_post_delay_is_within_the_configured_interval():
    assert server.AUTO_POST_MIN_SECONDS == 120
    assert server.AUTO_POST_MAX_SECONDS == 480
    for _ in range(20):
        delay = server.auto_post_delay()
        assert server.AUTO_POST_MIN_SECONDS <= delay <= server.AUTO_POST_MAX_SECONDS


def test_every_persona_gets_the_shared_prompt_with_the_roster():
    prompt = server.system_prompt_for(server.PERSONAS["eliade"])
    # promptul propriu rămâne primul, promptul comun se adaugă după
    assert prompt.startswith(server.PERSONAS["eliade"]["system_prompt"])
    # ceilalți participanți sunt listați cu handle-ul de @, ca să-i poată chema
    for pid in ALL_PERSONA_IDS:
        if pid != "eliade":
            assert f"(@{pid})" in prompt
    # dar nu se listează pe sine
    assert "(@eliade)" not in prompt


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
    # mesajele celorlalți sunt etichetate cu autorul, ca modelul să știe
    # cine ce a spus; propriile mesaje rămân neetichetate (rol assistant)
    assert payload["messages"] == [
        {"role": "system", "content": server.system_prompt_for(persona)},
        {"role": "user", "content": "[Utilizatorul]: salut"},
        {"role": "assistant", "content": "hop și-așa"},
        {"role": "user", "content": "[Utilizatorul]: ce mai faci?"},
    ]


def test_other_personas_messages_are_labeled_with_their_name(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "hm"}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)

    history = [
        {"author": "eliade", "text": "sacrul e peste tot", "timestamp": "acum"},
    ]
    asyncio.run(server.ask_ollama(server.PERSONAS["bunica"], history))

    assert captured["payload"]["messages"][1] == {
        "role": "user",
        "content": "[Mircea Eliade]: sacrul e peste tot",
    }
