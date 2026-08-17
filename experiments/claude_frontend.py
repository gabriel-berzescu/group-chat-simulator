"""„Claude-frontend": vorbește direct cu backend-ul, fără browser.

Importă server.py, izolează conversațiile în experiments/conversations/
(ignorat de git) și generează postări automate cu Ollama-ul real, măsurând
comportamentul personajelor: cât de des se mențin unele pe altele, cât de
lungi sunt replicile, cât durează generarea.

Exemple:
    python experiments/claude_frontend.py 6
    python experiments/claude_frontend.py 6 --message "salut! ce mai ziceti?"
    python experiments/claude_frontend.py 6 --shared-prompt-file varianta_b.txt

Serverul pornit cu uvicorn nu e afectat (nici conversațiile lui).
"""

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.chdir(REPO)  # server.py montează static/ relativ la directorul curent

import server

server.CONVERSATIONS_DIR = Path(__file__).parent / "conversations"
server.load_conversations()


def known_mentions(text: str) -> list[str]:
    return [p["id"] for p in server.mentioned_personas(text)]


EXAMPLE_PHRASES = ["tu ce zici", "tu cum vezi asta", "ia zi,", "matale ce sfat"]


async def run(args: argparse.Namespace) -> None:
    if args.shared_prompt_file:
        server.SHARED_SYSTEM_PROMPT = Path(args.shared_prompt_file).read_text(
            encoding="utf-8"
        )

    conversation = server.new_conversation()
    print(f"== conversatie {conversation['id']} ==")
    if args.message:
        conversation["messages"].append(
            {"author": "user", "text": args.message, "timestamp": "experiment"}
        )
        server.save_conversation(conversation)
        print(f"[user] {args.message}")

    stats = {"mentions": 0, "copycat": 0, "words": [], "seconds": [], "distinct": []}
    for i in range(args.rounds):
        pending = server.pending_mentions(conversation["messages"])
        start = time.monotonic()
        reply = await server.auto_post_once()
        elapsed = time.monotonic() - start
        mentions = known_mentions(reply["text"])
        words = len(reply["text"].split())

        stats["mentions"] += bool(mentions)
        stats["copycat"] += any(p in reply["text"].lower() for p in EXAMPLE_PHRASES)
        stats["words"].append(words)
        stats["seconds"].append(elapsed)
        stats["distinct"].append(len(set(mentions)))

        flat = " ".join(reply["text"].split())
        print(
            f"\n[{i + 1}] chemati inainte: {sorted(pending) or '-'}"
            f"\n[{reply['author']}] {flat}"
            f"\n    mentiuni={mentions or '-'} cuvinte={words} durata={elapsed:.0f}s"
        )

    n = args.rounds
    print(
        f"\n== sumar ({n} postari) =="
        f"\nreplici cu mentiuni:   {stats['mentions']}/{n}"
        f"\nmentiuni distincte/replica (medie): {sum(stats['distinct']) / n:.1f}"
        f"\nreplici cu formulari copiate din exemple: {stats['copycat']}/{n}"
        f"\ncuvinte/replica (medie): {sum(stats['words']) / n:.0f}"
        f"\ndurata/replica (medie):  {sum(stats['seconds']) / n:.0f}s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rounds", type=int, nargs="?", default=6)
    parser.add_argument("--message", help="mesaj de utilizator care deschide discuția")
    parser.add_argument(
        "--shared-prompt-file",
        help="fișier cu un shared_system_prompt alternativ (pentru A/B testing)",
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
