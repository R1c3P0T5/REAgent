from __future__ import annotations

import asyncio

from reagent.session import Session
from reagent.session.turn import run_turn


async def run(session: Session) -> None:
    loop = asyncio.get_running_loop()
    while True:
        try:
            prompt = await loop.run_in_executor(None, lambda: input("\033[36m> \033[0m"))
        except (EOFError, KeyboardInterrupt):
            break

        if prompt.strip().lower() in ("/quit", "/exit"):
            break

        session.add_user(prompt)
        await run_turn(session)
        print()


def start(session: Session) -> None:
    asyncio.run(run(session))
