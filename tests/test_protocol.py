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


def test_terminal_sink_on_assistant_empty_no_output(capsys):
    TerminalSink().on_assistant("")
    assert capsys.readouterr().out == ""


def test_terminal_sink_on_think(capsys):
    TerminalSink().on_think("reasoning")
    assert "reasoning" in capsys.readouterr().out


def test_terminal_sink_on_tool_call(capsys):
    TerminalSink().on_tool_call("bash", {"cmd": "ls"})
    assert "bash" in capsys.readouterr().out


def test_terminal_sink_on_tool_result(capsys):
    TerminalSink().on_tool_result("id1", "some output")
    assert "some output" in capsys.readouterr().out


def test_terminal_sink_on_status(capsys):
    TerminalSink().on_status("compacting...")
    assert "compacting..." in capsys.readouterr().out
