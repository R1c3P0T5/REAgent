from __future__ import annotations

import sys
from pathlib import Path


# Some runners execute the `pytest` entrypoint script directly (e.g. `uv run pytest`),
# which sets `sys.path[0]` to the script directory (like `.venv/bin`) instead of the
# repository root. Ensure the repo root is on sys.path so imports like
# `scripts.check_commit_msg` work reliably.
REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)
