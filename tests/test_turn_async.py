import inspect
from reagent.session.turn import run_turn


def test_run_turn_is_coroutine():
    """run_turn 必須是 async def"""
    assert inspect.iscoroutinefunction(run_turn)
