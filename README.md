# Group Chat Simulator

Un chat de grup simulat: tu + trei personaje fictive care vorbesc între ele și
îți răspund. Replicile personajelor sunt generate de un LLM local prin
[Ollama](https://ollama.com), deci totul rulează pe calculatorul tău, fără
niciun API extern.

Proiect făcut la un curs de vibe coding. Spec-ul complet e în [SPEC.md](SPEC.md).

> **Status:** în lucru — deocamdată există spec-ul și personajele, aplicația urmează.

## Personajele

| Personaj | Descriere |
|---|---|
| 🎤 Cântărețul de muzică populară | Haios, jovial, vorbește în metafore |
| 📚 Mircea Eliade | Istoricul religiilor, în persoană |
| 😎 Șmecherașul | Vrea să câștige și el ceva din orice conversație |

Definițiile (system prompt + temperature) sunt în `personaj1.md`–`personaj3.md`.

## Cum funcționează

```
Browser (frontend) ⇄ Backend FastAPI ⇄ Ollama (LLM local)
```

Backend-ul ține conversația în memorie, construiește prompt-ul fiecărui
personaj și cheamă Ollama pentru fiecare replică. Personajele postează singure
la intervale aleatorii, iar când scrii tu ceva, unul dintre ele îți răspunde
imediat.

## Cerințe

- Python 3.10+
- [Ollama](https://ollama.com/download) instalat și pornit
- Un model mic descărcat local, de exemplu:

```
ollama pull llama3.2:3b
```

## Pornire rapidă

```
pip install -r requirements.txt
uvicorn server:app
```

Apoi deschide http://localhost:8000 în browser și intră în vorbă.

Modelul folosit se poate schimba printr-o variabilă de mediu (vezi SPEC.md).
