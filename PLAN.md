# Plan de implementare

Planul e împărțit pe faze astfel încât la finalul **Fazei 1** să existe deja o
felie verticală completă (browser → FastAPI → Ollama → înapoi în browser).
Detaliile de produs sunt în [SPEC.md](SPEC.md).

## Faza 0 — Scheletul proiectului

- [ ] `requirements.txt` (fastapi, uvicorn, httpx)
- [ ] `server.py` cu FastAPI care servește `static/` și un `GET /api/health`
      care verifică și dacă Ollama răspunde pe `localhost:11434`
- [ ] `static/index.html` minimal ("Group Chat Simulator")

**Test:** `uvicorn server:app` pornește, pagina se încarcă, health check-ul
spune dacă Ollama e viu. Prinde din start problemele de mediu (Ollama nepornit,
model nedescărcat).

## Faza 1 — Felia verticală 🎯

Chat funcțional cu **un singur personaj** (Cântărețul), fără automatisme:

- [ ] Stocarea mesajelor în memorie (listă simplă: autor, text, timestamp)
- [ ] `GET /api/messages` + `POST /api/messages`
- [ ] La POST, backend-ul construiește promptul (system prompt din personaj +
      istoricul) și cheamă Ollama sincron; răspunsul se adaugă în listă
- [ ] UI minimal: lista de mesaje + input jos, polling la 1–2 secunde

**Test:** scrii "salut" în browser și primești o metaforă populară înapoi.
Din acest punct aplicația e demo-abilă cap-coadă — tot ce urmează se adaugă
pe o fundație care merge.

## Faza 2 — Cele 3 personaje

- [ ] `personas.py` cu definițiile din `personaj1–3.md` (nume, emoji,
      system prompt, temperature)
- [ ] `GET /api/personas` și afișarea numelui + emoji-ului lângă fiecare
      mesaj în UI
- [ ] Logica de alegere: cine răspunde utilizatorului (aleator e suficient
      pentru MVP, eventual cu regula "nu același personaj de două ori la rând")

**Test:** răspund personaje diferite, fiecare cu vocea lui.

## Faza 3 — Chatul "viu"

- [ ] Task de fundal (asyncio) în care personajele postează singure la
      intervale aleatorii. În timpul dezvoltării: 10–30 secunde, configurabil;
      default-ul "de producție" rămâne 2–8 minute, ca în spec.
- [ ] Indicatorul "X is typing…": un flag pe backend expus prin
      `GET /api/messages` (sau un endpoint separat), afișat de UI cât timp
      se așteaptă Ollama

**Test:** lași pagina deschisă și personajele încep să vorbească singure.

*Notă:* typing indicator-ul apare în spec la MVP, dar l-am mutat aici pentru
că în Faza 1 răspunsul e sincron și indicatorul n-ar avea încă ce arăta.

## Faza 4 — Robustețe și finisaj

- [ ] Model configurabil prin variabilă de mediu (`OLLAMA_MODEL`,
      default `llama3.2:3b`)
- [ ] Tratarea erorilor: Ollama căzut sau timeout → mesaj de sistem în chat,
      nu crash
- [ ] Limitarea istoricului trimis la Ollama (ultimele N mesaje) ca să nu
      explodeze contextul pe model mic
- [ ] CSS decent (bule de chat, culori pe personaj), auto-scroll
- [ ] Actualizarea README-ului ca "Pornire rapidă" să fie 100% adevărată —
      criteriul de succes din spec

## După (v0.2+, opțional, în ordinea valorii)

1. Personajele își răspund unul altuia (conversație emergentă) — cel mai
   spectaculos vizual
2. Streaming (SSE) în loc de polling
3. Persistență în JSON/SQLite
4. Editor de personaje din UI
