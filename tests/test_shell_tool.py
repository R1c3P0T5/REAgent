import asyncio
import signal
from types import SimpleNamespace

import pytest

from reagent.results import ShellResult
from reagent.tools import shell


def test_run_shell_returns_output(monkeypatch):
    monkeypatch.setattr(
        shell.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="hello\n", stderr=""),
    )

    result = shell.run_shell("echo hello", timeout=1)

    assert isinstance(result, ShellResult)
    assert result.text == "hello"


@pytest.mark.parametrize("returncode", [-signal.SIGINT, 128 + signal.SIGINT])
def test_run_shell_interrupt_returncode_cancels_turn(monkeypatch, returncode):
    monkeypatch.setattr(
        shell.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=returncode, stdout="", stderr=""),
    )

    with pytest.raises(asyncio.CancelledError):
        shell.run_shell("sleep 10", timeout=1)
