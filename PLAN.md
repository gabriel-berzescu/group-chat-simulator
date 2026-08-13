# Plan de implementare

Planul e împărțit pe faze astfel încât la finalul **Fazei 1** să existe deja o
felie verticală completă (browser → FastAPI → Ollama → înapoi în browser).
Detaliile de produs sunt în [SPEC.md](SPEC.md).

## Mod de lucru — Test Driven Development

Lucrăm în TDD, în ciclul clasic red–green–refactor:

1. **Red** — scriem întâi testul pentru comportamentul nou și îl vedem picând.
2. **Green** — scriem implementarea minimă care face testul să treacă.
3. **Refactor** — curățăm codul, cu testele verzi ca plasă de siguranță.

Concret pentru proiectul ăsta:

- Testele stau în `test_server.py` și rulează cu `pytest`, folosind
  `TestClient`-ul din FastAPI (nu e nevoie de server pornit).
- **Ollama nu e chemat din teste** — apelurile HTTP către el se mock-uiesc,
  ca testele să fie rapide și deterministe.
- Secțiunile "**Test:**" de la finalul fiecărei faze rămân ca verificare
  manuală de acceptanță (în browser, cu Ollama real); ele completează
  testele automate, nu le înlocuiesc.

## Faza 0 — Scheletul proiectului

- [x] `requirements.txt` (fastapi, uvicorn, httpx)
- [x] `server.py` cu FastAPI care servește `static/` și un `GET /api/health`
      care verifică și dacă Ollama răspunde pe `localhost:11434`
- [x] `static/index.html` minimal ("Group Chat Simulator")

**Test:** `uvicorn server:app` pornește, pagina se încarcă, health check-ul
spune dacă Ollama e viu. Prinde din start problemele de mediu (Ollama nepornit,
model nedescărcat).

## Faza 1 — Felia verticală 🎯

Chat funcțional cu **un singur personaj** (Cântărețul), fără automatisme:

- [x] Stocarea mesajelor în memorie (listă simplă: autor, text, timestamp)
- [x] `GET /api/messages` + `POST /api/messages`
- [x] La POST, backend-ul construiește promptul (system prompt din personaj +
      istoricul) și cheamă Ollama sincron; răspunsul se adaugă în listă
- [x] UI minimal: lista de mesaje + input jos, polling la 1–2 secunde

**Test:** scrii "salut" în browser și primești o metaforă populară înapoi.
Din acest punct aplicația e demo-abilă cap-coadă — tot ce urmează se adaugă
pe o fundație care merge.

## Faza 2 — Cele 3 personaje

- [x] Personajele se citesc din fișierul de configurare `personas.json`
      (nume, emoji, system prompt, temperature pentru fiecare)
- [x] `GET /api/personas` și afișarea numelui + emoji-ului lângă fiecare
      mesaj în UI
- [x] Logica de alegere: dacă utilizatorul menționează personaje cu `@`
      (ex. `@Șmecherașul`), răspund doar cele menționate; dacă mesajul nu
      conține nicio mențiune, răspund toate personajele. *Regulă provizorie,
      doar pentru faza asta — o orchestrare mai deșteaptă vine într-o fază
      ulterioară, tot în MVP (de detaliat).*

**Test:** un mesaj cu `@personaj` primește răspuns doar de la cel menționat;
un mesaj fără mențiuni primește răspuns de la toate trei, fiecare cu vocea lui.

## Faza 2b — Conversații multiple, persistate în JSON

Mesajele nu se mai pierd la restart: fiecare conversație se salvează într-un
fișier JSON propriu, iar din UI poți vedea toate conversațiile, comuta între
ele și începe una nouă.

**Backend:**

- [x] Directorul `conversations/` (creat automat, ignorat de git) în care
      fiecare conversație are propriul fișier, ex.
      `conversations/2026-08-13T10-30-00.json`
- [x] Formatul fișierului: un obiect JSON cu id-ul conversației, data creării
      și lista de mesaje (autor, text, timestamp)
- [x] La pornirea serverului se încarcă toate conversațiile existente de pe
      disc; dacă nu există niciuna, se creează una nouă
- [x] `GET /api/conversations` — lista conversațiilor (id, data creării,
      numărul de mesaje), sortată descrescător după creare
- [x] `POST /api/conversations` — creează o conversație nouă (goală) și
      întoarce id-ul ei
- [x] Mesajele devin per-conversație:
      `GET/POST /api/conversations/{id}/messages` înlocuiesc
      `GET/POST /api/messages` (istoricul trimis la Ollama e cel al
      conversației respective)
- [x] După fiecare mesaj adăugat (al utilizatorului sau al unui personaj),
      conversația respectivă se rescrie în fișierul ei

**UI:**

- [x] Listă de conversații (dropdown în header) cu buton „Conversație nouă"
- [x] Click pe o conversație o încarcă în fereastra de chat; polling-ul de
      mesaje se face pe conversația selectată
- [x] La încărcarea paginii se deschide cea mai recentă conversație

În teste directorul de conversații se configurează (ex. prin `tmp_path` din
pytest), ca testele să nu scrie în directorul real.

*Notă pentru Faza 3:* personajele vor posta automat doar în conversația
activă (cea mai recent folosită), nu în toate.

**Test:** porți o conversație, repornești serverul și o regăsești întreagă în
UI; creezi o conversație nouă, scrii în ea, apoi comuți înapoi la cea veche și
ambele își păstrează mesajele (și fișierele JSON aferente pe disc).

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
      default `gemma4:e2b`)
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
3. Persistență în SQLite (JSON-ul e acoperit de Faza 2b); redenumirea și
   ștergerea conversațiilor din UI
4. Editor de personaje din UI
