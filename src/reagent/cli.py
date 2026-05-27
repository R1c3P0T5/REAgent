from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("LITELLM_LOG", "ERROR")

from reagent.repl import run  # noqa: E402
from reagent.session import Session  # noqa: E402


def main() -> int:
    session = Session()
    run(session)
    return 0
