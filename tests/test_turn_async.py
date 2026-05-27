import inspect
from reagent.session.turn import run_turn


def test_run_turn_is_coroutine():
    assert inspect.iscoroutinefunction(run_turn)
