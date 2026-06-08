# REAgent

## Quick Start

Start a new session:

```sh
reagent
```

Resume a session by UUID:

```sh
reagent --resume <session>
```

help:

```shell-session
$ reagent -h
Usage: reagent [OPTIONS] COMMAND [ARGS]...

Options:
  --resume TEXT  Resume a session by JSONL path or session UUID
  -h, --help     Show this message and exit.

Commands:
  completion  generate shell completion script
  providers   manage AI providers and credentials
```

## Configuration

Copy `config.toml.example` to `config.toml` and set at least the model:

```toml
[llm]
model = "anthropic/claude-sonnet-4-6"
```

## Shell Completion

Add the matching command to your shell startup file:

```sh
# ~/.bashrc
eval "$(reagent completion bash)"
```

```sh
# ~/.zshrc
eval "$(reagent completion zsh)"
```

```fish
# ~/.config/fish/config.fish
reagent completion fish | source
```
