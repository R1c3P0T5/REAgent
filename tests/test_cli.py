from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from typer.testing import CliRunner

from reagent import cli
from reagent.cli import build_session


def test_importing_cli_does_not_load_repl_or_litellm():
    script = (
        "import sys; "
        "import reagent.cli; "
        "print('dotenv' in sys.modules); "
        "print('reagent.config' in sys.modules); "
        "print('reagent.session' in sys.modules); "
        "print('reagent.repl' in sys.modules); "
        "print('litellm' in sys.modules); "
        "print('LITELLM_LOG' in __import__('os').environ)"
    )
    env = os.environ.copy()
    env.pop("LITELLM_LOG", None)

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.splitlines() == ["False", "False", "False", "False", "False", "False"]


def test_build_session_allocates_recorder_without_creating_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REAGENT_HOME", str(tmp_path))
    monkeypatch.setenv("MODEL_ID", "test-model")

    session = build_session()

    assert session._recorder is not None
    assert not session._recorder.path.exists()
    assert session._recorder.path.is_relative_to(tmp_path / "sessions")


def test_build_session_resumes_existing_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REAGENT_HOME", str(tmp_path))
    monkeypatch.setenv("MODEL_ID", "test-model")
    session = build_session()
    session.add_user("hello")

    assert session._recorder is not None
    resumed = build_session(resume=os.fspath(session._recorder.path))

    assert resumed._recorder is not None
    assert resumed._recorder.path == session._recorder.path
    assert resumed.messages == ({"role": "user", "content": "hello"},)


def test_build_session_records_config_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REAGENT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("MODEL_ID", raising=False)
    Path(tmp_path / "home").mkdir()
    Path(tmp_path / "home" / "config.toml").write_text(
        '[llm]\nmodel = "test-config-model"\n',
        encoding="utf-8",
    )

    session = build_session()
    session.add_user("hello")

    assert session._recorder is not None
    meta_line = session._recorder.path.read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(meta_line)["data"]["model"] == "test-config-model"


def test_providers_login_writes_key_to_user_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REAGENT_HOME", str(tmp_path))

    result = cli.main(["providers", "login", "openai", "--key", "sk-test"])

    assert result == 0
    assert (tmp_path / "config.toml").read_text(encoding="utf-8") == ('[providers.openai]\nkey = "sk-test"\n')


def test_providers_logout_removes_key_from_user_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REAGENT_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        '[providers.openai]\nkey = "sk-test"\nbase_url = "https://example.test/v1"\n',
        encoding="utf-8",
    )

    result = cli.main(["providers", "logout", "openai"])

    assert result == 0
    assert (tmp_path / "config.toml").read_text(encoding="utf-8") == (
        '[providers.openai]\nbase_url = "https://example.test/v1"\n'
    )


def test_providers_logout_does_not_create_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REAGENT_HOME", str(tmp_path))

    result = cli.main(["providers", "logout", "openai"])

    assert result == 0
    assert not (tmp_path / "config.toml").exists()


def test_providers_list_does_not_require_llm_model(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REAGENT_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text('[providers.openai]\nkey = "sk-test"\n', encoding="utf-8")

    result = cli.main(["providers", "list"])

    assert result == 0
    assert "openai" in capsys.readouterr().out


def test_typer_app_resumes_session(monkeypatch):
    started = []
    config = object()

    def fake_build_session(*, resume=None, sink=None, config=None):
        assert sink is None
        assert config is not None
        return {"resume": resume}

    def fake_start(session, cfg):
        started.append((session, cfg))

    monkeypatch.setattr(cli, "build_session", fake_build_session)
    monkeypatch.setattr("reagent.repl.start", fake_start)
    monkeypatch.setattr("reagent.config.load", lambda: config)
    monkeypatch.setattr("reagent.config.apply_provider_env", lambda _: None)

    result = CliRunner().invoke(cli.app, ["--resume", "session-id"])

    assert result.exit_code == 0
    assert started == [({"resume": "session-id"}, config)]


def test_typer_app_accepts_short_help():
    result = CliRunner().invoke(cli.app, ["-h"])

    assert result.exit_code == 0


def test_main_reports_unknown_option_without_traceback(capsys):
    result = cli.main(["--bad-arg"])

    captured = capsys.readouterr()
    assert result != 0
    assert "Traceback" not in captured.err


def test_completion_generates_shell_script():
    for shell in ("bash", "zsh", "fish"):
        result = CliRunner().invoke(cli.app, ["completion", shell])

        assert result.exit_code == 0
        assert result.output


def test_completion_probe_uses_typer_instruction_format():
    result = CliRunner().invoke(
        cli.app,
        [],
        prog_name="reagent",
        env={
            "_REAGENT_COMPLETE": "complete_zsh",
            "COMP_WORDS": "reagent ",
            "COMP_CWORD": "1",
        },
    )

    assert result.exit_code == 0
    assert "Shell complete not supported" not in result.output


def test_main_handles_completion_probe_without_running_repl():
    script = "from reagent.cli import main; raise SystemExit(main([]))"
    env = os.environ | {
        "_REAGENT_COMPLETE": "complete_zsh",
        "_TYPER_COMPLETE_ARGS": "reagent ",
    }

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout
    assert "Shell complete not supported" not in result.stderr
    assert "Traceback" not in result.stderr


def test_completion_command_does_not_load_runtime_env():
    script = (
        "import os; "
        "from reagent.cli import main; "
        "code = main(['completion', 'bash']); "
        "print('LITELLM_LOG_LOADED', 'LITELLM_LOG' in os.environ); "
        "raise SystemExit(code)"
    )
    env = os.environ.copy()
    env.pop("LITELLM_LOG", None)

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "LITELLM_LOG_LOADED False" in result.stdout


def test_completion_rejects_unknown_shell_without_traceback():
    result = CliRunner().invoke(cli.app, ["completion", "powershell"])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
