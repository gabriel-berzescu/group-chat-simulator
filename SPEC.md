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
- Când utilizatorul scrie un mesaj, backend-ul alege un personaj care îi
  răspunde (imediat, nu la intervalul lung).
- Indicator "X is typing…" cât timp backend-ul așteaptă răspunsul de la Ollama.
- Conversația trăiește în memoria backend-ului (se pierde la restart — e OK).

## Tehnologii

- **Backend:** Python + FastAPI (rulat cu uvicorn), un singur fișier de
  pornire; apelează Ollama prin API-ul HTTP local (`POST /api/chat` pe
  `localhost:11434`), cu `httpx` sau `requests`.
- **Model:** un model mic care merge pe laptop (ex. `llama3.2:3b`) —
  configurabil printr-o variabilă de mediu.
- **Frontend:** HTML + CSS + JavaScript vanilla, servit static de backend;
  fără framework, fără build step. Polling simplu (`GET /api/messages`)
  pentru mesaje noi — fără WebSockets în MVP.
- Structură sugerată:

```
server.py        — FastAPI + endpoints + logica personajelor
personas.py      — definițiile personajelor (nume, emoji, system prompt)
requirements.txt — dependențe (fastapi, uvicorn, httpx)
static/
  index.html
  style.css
  app.js
```

### API minimal

- `GET  /api/messages` — toate mesajele conversației.
- `POST /api/messages` — utilizatorul trimite un mesaj.
- `GET  /api/personas` — lista personajelor (pentru afișare în UI).

## Ne-scopuri (deocamdată)

- Fără persistență (baze de date, fișiere) și fără autentificare.
- Fără WebSockets/SSE — polling e suficient.
- Fără mai multe camere/canale sau mai mulți utilizatori simultan.

## Extensii posibile (v0.2+)

1. Streaming al răspunsurilor (SSE/WebSockets) în loc de polling.
2. Salvarea conversației (fișier JSON sau SQLite).
3. Editor de personaje (adaugi/modifici personalități din UI).
4. Reacții cu emoji la mesaje.
5. Personajele își răspund unul altuia (conversație emergentă între boți).

## Criterii de succes

- Cineva cu Ollama instalat poate clona repo-ul, rula
  `pip install -r requirements.txt` și `uvicorn server:app`, și vedea
  chat-ul "viu" în câteva minute.
