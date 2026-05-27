# tests/test_session_sink.py
from reagent.protocol import SilentSink
from reagent.session.session import Session


def test_session_defaults_to_terminal_sink():
    from reagent.protocol import TerminalSink

    s = Session()
    assert isinstance(s._sink, TerminalSink)


def test_session_accepts_custom_sink():
    sink = SilentSink()
    s = Session(sink=sink)
    assert s._sink is sink


def test_add_assistant_calls_sink(capsys):
    s = Session(sink=SilentSink())
    s.add_assistant("hello")
    assert capsys.readouterr().out == ""


def test_add_think_calls_sink(capsys):
    s = Session(sink=SilentSink())
    s.add_think("thinking...")
    assert capsys.readouterr().out == ""


def test_add_tool_result_calls_sink(capsys):
    s = Session(sink=SilentSink())
    s.add_tool_result("id1", "output")
    assert capsys.readouterr().out == ""


def test_emit_tool_call_calls_sink(capsys):
    s = Session(sink=SilentSink())
    s.emit_tool_call("bash", {"cmd": "ls"})
    assert capsys.readouterr().out == ""


def test_emit_status_calls_sink(capsys):
    s = Session(sink=SilentSink())
    s.emit_status("compacting...")
    assert capsys.readouterr().out == ""
