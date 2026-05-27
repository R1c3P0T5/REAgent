from __future__ import annotations

from reagent.session import Session
from reagent.session.turn import run_turn


def run(session: Session) -> None:
    while True:
        try:
            prompt = input("\033[36m> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break

        if prompt.strip().lower() in ("/quit", "/exit"):
            break

        session.add_user(prompt)
        run_turn(session)
        print()
