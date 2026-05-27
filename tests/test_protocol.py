# tests/test_protocol.py
from reagent.protocol import OutputSink, SilentSink, TerminalSink


def test_terminal_sink_implements_protocol():
    assert isinstance(TerminalSink(), OutputSink)


def test_silent_sink_implements_protocol():
    assert isinstance(SilentSink(), OutputSink)


def test_silent_sink_produces_no_output(capsys):
    sink = SilentSink()
    sink.on_assistant("hello")
    sink.on_think("thinking")
    sink.on_tool_call("bash", {"cmd": "ls"})
    sink.on_tool_result("id1", "result")
    sink.on_status("status msg")
    assert capsys.readouterr().out == ""


def test_terminal_sink_on_assistant(capsys):
    TerminalSink().on_assistant("hello")
    assert "hello" in capsys.readouterr().out
