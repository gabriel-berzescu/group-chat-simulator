# Group Chat Simulator — Spec minimal

## Ce este

O aplicație web care simulează un chat de grup: utilizatorul intră într-o
"conversație" cu mai multe personaje fictive (boți cu personalități diferite)
care își scriu între ei și îi răspund. Răspunsurile personajelor sunt generate
de un LLM local prin **Ollama**. Proiect educațional pentru curs — scopul e să
fie simplu de rulat și extins.

## Arhitectură

```
Browser (frontend) ⇄ Backend (API HTTP) ⇄ Ollama (LLM local, localhost:11434)
```

- Frontend-ul nu vorbește niciodată direct cu Ollama — totul trece prin backend.
- Backend-ul ține starea conversației și construiește prompt-ul fiecărui
  personaj (personalitate + istoricul chatului).

## MVP (v0.1)

- O singură pagină web cu interfață de chat clasică: listă de mesaje + input jos.
- 3 personaje predefinite, fiecare cu nume, avatar (emoji) și personalitate
  distinctă (ex: entuziastul, scepticul, cel care schimbă subiectul), definite
  ca system prompt-uri pe backend.
- Personajele trimit mesaje automat, la intervale aleatorii (2–8 minute),
  generate de Ollama pe baza personalității și a istoricului conversației.
- Când utilizatorul scrie un mesaj, îi răspunde (imediat, nu la intervalul
  lung) un singur personaj, tras la sorți: personajele menționate cu `@`
  (ex. `@Șmecherașul`) care n-au apucat să posteze de la mențiune împart
  egal 80% din șanse, iar celelalte restul de 20%. Mențiunile se acumulează
  din tot istoricul conversației — și personajele se pot menționa între
  ele — și se sting când personajul respectiv postează. Fără nicio mențiune
  în așteptare, șansele sunt egale.
- Indicator "X is typing…" cât timp backend-ul așteaptă răspunsul de la Ollama.
- Conversații multiple, persistate pe disc: fiecare conversație are propriul
  fișier JSON în `conversations/`, scris după fiecare mesaj și reîncărcat la
  pornirea serverului. Din UI poți vedea lista conversațiilor, comuta între
  ele și începe una nouă; personajele postează automat doar în conversația
  activă.

## Tehnologii

- **Backend:** Python + FastAPI (rulat cu uvicorn), un singur fișier de
  pornire; apelează Ollama prin API-ul HTTP local (`POST /api/chat` pe
  `localhost:11434`), cu `httpx` sau `requests`.
- **Model:** un model mic care merge pe laptop (ex. `gemma4:e2b`) —
  configurabil printr-o variabilă de mediu.
- **Frontend:** HTML + CSS + JavaScript vanilla, servit static de backend;
  fără framework, fără build step. Polling simplu
  (`GET /api/conversations/{id}/messages`) pentru mesaje noi — fără
  WebSockets în MVP.
- **Teste:** `pytest` + `TestClient`-ul din FastAPI; dezvoltarea se face
  test-first (vezi [PLAN.md](PLAN.md)), cu Ollama mock-uit în teste.
- Structură sugerată:

```
server.py        — FastAPI + endpoints + logica personajelor
personas.json    — definițiile personajelor (nume, emoji, system prompt, temperature)
test_server.py   — teste (pytest)
requirements.txt — dependențe (fastapi, uvicorn, httpx, pytest)
conversations/   — câte un fișier JSON per conversație (creat la rulare, ignorat de git)
static/
  index.html     — pagina (CSS-ul stă inline aici, nu în fișier separat)
  app.js
```

### API minimal

- `GET  /api/conversations` — lista conversațiilor (id, data creării,
  numărul de mesaje).
- `POST /api/conversations` — începe o conversație nouă.
- `GET  /api/conversations/{id}/messages` — mesajele unei conversații.
- `POST /api/conversations/{id}/messages` — utilizatorul trimite un mesaj
  în conversația respectivă.
- `GET  /api/personas` — lista personajelor (pentru afișare în UI).

*(În fazele timpurii, până la introducerea conversațiilor multiple,
endpoint-urile de mesaje există în forma simplă `GET/POST /api/messages`.)*

## Ne-scopuri (deocamdată)

- Fără baze de date (persistența e doar în fișiere JSON) și fără autentificare.
- Fără WebSockets/SSE — polling e suficient.
- Fără mai mulți utilizatori simultan — un singur utilizator, o singură
  conversație activă la un moment dat (dar poate comuta între conversații).

## Extensii posibile (v0.2+)

1. Streaming al răspunsurilor (SSE/WebSockets) în loc de polling.
2. Persistență în SQLite (salvarea în JSON e deja în MVP); redenumirea și
   ștergerea conversațiilor din UI.
3. Editor de personaje (adaugi/modifici personalități din UI).
4. Reacții cu emoji la mesaje.
5. Personajele își răspund unul altuia (conversație emergentă între boți).

## Criterii de succes

- Cineva cu Ollama instalat poate clona repo-ul, rula
  `pip install -r requirements.txt` și `uvicorn server:app`, și vedea
  chat-ul "viu" în câteva minute.
