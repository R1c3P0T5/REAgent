from __future__ import annotations

from enum import Enum
import getpass
import os
from typing import Annotated, Any

import typer
from typer._completion_shared import get_completion_script

_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class CompletionShell(str, Enum):
    bash = "bash"
    zsh = "zsh"
    fish = "fish"


app = typer.Typer(
    add_completion=False,
    context_settings=_CONTEXT_SETTINGS,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
)
providers_app = typer.Typer(
    help="manage AI providers and credentials",
    context_settings=_CONTEXT_SETTINGS,
    rich_markup_mode=None,
)
app.add_typer(providers_app, name="providers")


def load_runtime_env() -> None:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True), override=True)
    os.environ.setdefault("LITELLM_LOG", "ERROR")


def build_session(resume: str | None = None, sink=None, config: Any = None) -> Any:
    load_runtime_env()

    from reagent.session import Session, SessionRecorder, find_file, load_session

    if resume is not None:
        path = find_file(resume)
        return load_session(path, sink=sink)

    if config is None:
        from reagent.config import load as load_config

        config = load_config()

    recorder = SessionRecorder.create(cwd=os.getcwd(), model=config.llm.model)
    return Session(sink=sink, recorder=recorder)


@app.callback(invoke_without_command=True)
def run(
    ctx: typer.Context,
    resume: Annotated[str | None, typer.Option(help="Resume a session by JSONL path or session UUID")] = None,
) -> None:
    if ctx.invoked_subcommand is not None:
        return

    load_runtime_env()

    from reagent.config import apply_provider_env, load as load_config

    config = load_config()
    apply_provider_env(config)

    session = build_session(resume=resume, config=config)

    from reagent.repl import start

    start(session, config)


@app.command(help="generate shell completion script")
def completion(shell: CompletionShell) -> None:
    typer.echo(
        get_completion_script(
            prog_name="reagent",
            complete_var="_REAGENT_COMPLETE",
            shell=shell,
        ),
        nl=False,
    )


@providers_app.command("list")
def list_providers() -> None:
    load_runtime_env()

    from reagent.config import load_layers

    layers = load_layers()
    for name, provider in sorted(layers.config.providers.items()):
        status = "logged-in" if provider.key else "logged-out"
        typer.echo(f"{name}\t{status}")


@providers_app.command()
def login(
    provider: str,
    key: Annotated[str | None, typer.Option(help="API key to store; prompts when omitted")] = None,
) -> None:
    load_runtime_env()

    from reagent.config import set_provider_key

    set_provider_key(provider, key or getpass.getpass(f"{provider} API key: "))
    typer.echo(f"{provider}\tlogged-in")


@providers_app.command()
def logout(provider: str) -> None:
    load_runtime_env()

    from reagent.config import remove_provider_key

    remove_provider_key(provider)
    typer.echo(f"{provider}\tlogged-out")


def main(argv: list[str] | None = None) -> int:
    import click
    from typer._completion_classes import completion_init

    completion_init()

    try:
        result = app(args=argv, complete_var="_REAGENT_COMPLETE", standalone_mode=False)
        return result or 0

    except click.ClickException as exc:
        exc.show()
        return exc.exit_code

    except click.Abort:
        return 1
