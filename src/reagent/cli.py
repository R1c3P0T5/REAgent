from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("LITELLM_LOG", "ERROR")

from reagent.session import Session  # noqa: E402
from reagent.session.turn import run_turn  # noqa: E402


def main() -> int:
    session = Session()
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
    return 0
