# Group Chat Simulator

Un chat de grup simulat: tu + trei personaje fictive care vorbesc între ele și
îți răspund. Replicile personajelor sunt generate de un LLM local prin
[Ollama](https://ollama.com), deci totul rulează pe calculatorul tău, fără
niciun API extern.

Proiect făcut la un curs de vibe coding. Spec-ul complet e în [SPEC.md](SPEC.md).

> **Status:** în lucru — chatul e "viu": cele 9 personaje, mențiuni `@` cu
> tragere la sorți 80/20, conversații multiple persistate pe disc, postare
> automată la intervale aleatorii și indicator "typing". Urmează finisajele
> (Faza 4 din [PLAN.md](PLAN.md)).

## Personajele

| Personaj | Descriere |
|---|---|
| 🎤 Cântărețul de muzică populară | Haios, jovial, vorbește în metafore |
| 📚 Mircea Eliade | Istoricul religiilor, în persoană |
| 😎 Șmecherașul | Vrea să câștige și el ceva din orice conversație |
| 🎭 I.L. Caragiale | Ironic, spiritual, vede ridicolul din orice situație |
| 🧶 Bunica de la țară | Caldă, grijulie, dă sfaturi din bătrâni și vrea să hrănească pe toată lumea |
| 🚕 Taximetristul | Vorbăreț, are o părere despre orice, toate poveștile încep cu un client |
| 🤳 Influencerița | Multe englezisme, totul e „super cute", strecoară coduri de reducere |
| 💼 Corporatistul | Jargon de birou, mereu ocupat și obosit, se laudă cu team building-urile |
| 🧛 Contele Dracula | Teatral, aristocrat, se plânge de vremurile moderne |

Definițiile (system prompt + temperature) sunt în fișierul de configurare
`personas.json`, tot acolo fiind și `shared_system_prompt` — instrucțiuni
comune adăugate automat la promptul fiecărui personaj, cu lista celorlalți
participanți, ca să se poată chema unii pe alții cu `@`.

## Cum funcționează

```
Browser (frontend) ⇄ Backend FastAPI ⇄ Ollama (LLM local)
```

Backend-ul ține conversațiile în memorie și le salvează pe disc (câte un
fișier JSON per conversație, în `conversations/`), construiește prompt-ul
fiecărui personaj și cheamă Ollama pentru fiecare replică. Când scrii ceva,
îți răspunde imediat un singur personaj, tras la sorți: cele menționate cu
`@` — oriunde în conversație, chiar de alte personaje — și care n-au apucat
încă să răspundă împart 80% din șanse, restul 20% (fără mențiuni în
așteptare, șansele sunt egale). Personajele postează și singure, la intervale
aleatorii (implicit 2–8 minute), doar în conversația pe care o ai deschisă;
cât timp se generează o replică, în chat apare indicatorul "typing" cu
avatarul personajului. Din UI poți comuta între conversații sau începe
una nouă.

Intervalul postărilor automate se configurează prin variabile de mediu —
util în dezvoltare, ca să nu aștepți minute întregi:

```
$env:AUTO_POST_MIN_SECONDS = 10    # Windows (pe Linux/macOS: export AUTO_POST_MIN_SECONDS=10)
$env:AUTO_POST_MAX_SECONDS = 30
uvicorn server:app
```

## Cerințe

- Python 3.10+
- [Ollama](https://ollama.com/download) instalat și pornit
- Un model mic descărcat local, de exemplu:

```
ollama pull gemma4:e2b
```

## Pornire rapidă

```
python -m venv .venv
.venv\Scripts\activate     # Windows (pe Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn server:app
```

Apoi deschide http://localhost:8000 în browser și intră în vorbă.

Modelul e deocamdată fixat în `server.py` (`gemma4:e2b`); configurarea printr-o
variabilă de mediu (`OLLAMA_MODEL`) vine în Faza 4 (vezi PLAN.md).

## Teste

Proiectul e dezvoltat test-first (TDD). Testele nu au nevoie de Ollama pornit:

```
pytest
```

## Experimente

`experiments/claude_frontend.py` rulează personajele fără browser, cu Ollama
real, și măsoară cât de des se cheamă între ele cu `@`, cât de lungi sunt
replicile și cât durează generarea — util pentru A/B pe prompturi. Detalii și
rezultate în [experiments/README.md](experiments/README.md).
