# Experimente

`claude_frontend.py` vorbește direct cu backend-ul (importă `server.py`), fără
browser: generează postări automate cu Ollama-ul real și măsoară cum se poartă
personajele. Conversațiile lui stau în `experiments/conversations/` (ignorat de
git), deci nu ating conversațiile reale și nici serverul pornit cu uvicorn.

```
python experiments/claude_frontend.py 6
python experiments/claude_frontend.py 6 --message "unde merg in vacanta?"
python experiments/claude_frontend.py 6 --shared-prompt-file experiments/prompt_b.txt
```

Raportează, pentru fiecare replică: cine a postat, cine era „chemat" cu `@`
înainte, mențiunile recunoscute, lungimea și durata generării — plus un sumar.

## Ce am aflat (17 aug 2026, `gemma4:e2b`, 6 postări/variantă)

Personajele nu se menționau deloc între ele. Cauza s-a dovedit banală
(serverul rula cu prompturile vechi, dinainte de `shared_system_prompt`), dar
experimentele au scos la iveală două probleme reale de prompt:

| Variantă | Cu mențiuni | Mențiuni/replică | Formulări copiate | Cuvinte/replică |
|---|---|---|---|---|
| A — prompt inițial | 6/6 | 3.0 | 5/6 | 130 |
| B — „un singur participant", fără „nu rezuma" | 6/6 | 1.0 | 0/6 | 140 |
| C — B + istoric etichetat cu autorul | 6/6 | 1.0 | 0/6 | 89 |

- **Un singur exemplu de formulare în prompt = papagal.** Cu un singur exemplu
  („tu ce zici, @X?"), 5 din 6 replici îl copiau cuvânt cu cuvânt. Cu trei
  exemple variate, 0 din 6.
- **„Adresează-te des câte unuia" producea liste de 3 mențiuni** — replici de
  tip recap, care nu duceau discuția nicăieri. „Exact unui singur participant"
  a dat conversație pe lanț: fiecare pasează vorba mai departe.
- **Istoricul era anonim.** Toate mesajele celorlalți ajungeau la Ollama ca rol
  `user`, nediferențiate, așa că modelul nu știa cine ce a spus și atribuia
  greșit replicile (varianta B: Dracula i-a răspuns „@corporatistul" unei
  replici a Șmecherașului). Etichetarea cu `[Nume]: text` a rezolvat-o și, ca
  bonus, a scurtat replicile cu ~35% și generarea cu ~35%.

Varianta C e cea din `personas.json` și `server.py` acum. `prompt_b.txt` și
`prompt_c.txt` rămân ca punct de pornire pentru următoarele A/B-uri.

## Idei de explorat mai departe

- Un „regizor" care alege subiectul, ca discuția să nu alunece mereu spre
  metafore (toate variantele au ajuns la umbre și lumină în ~4 replici).
- Cât istoric merită trimis (Faza 4 taie oricum la ultimele N mesaje).
- Comparație între modele (`gemma4:e2b` vs. altele) pe aceleași metrici.
