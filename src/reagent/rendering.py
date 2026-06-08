from __future__ import annotations

import json
import re
import textwrap
import time
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich import box as rich_box
from rich.console import Console, Group
from rich.panel import Panel

if TYPE_CHECKING:
    from reagent.config import Config
    from reagent.session.session import Session
from rich.live import Live
from rich.markdown import Markdown
from rich.segment import Segment, Segments
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.theme import Theme
from rich.text import Text

from reagent.results import DiffResult, ErrorResult, ReadResult, ShellResult, ToolResult
from reagent.session.recorder import _client_version


SPINNER_FRAMES = "☰☱☲☳☴☵☶☷"
_SPINNER_MS = 80

# Strips ANSI/VT escape sequences so raw terminal output (gdb, vim, curses apps)
# cannot corrupt the rendering terminal when replayed or displayed as tool output.
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\))"
    r"|\x0e|\x0f"  # SO / SI character-set shifts
)


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


def _fmt_elapsed(elapsed: float) -> str:
    if elapsed >= 60:
        m = int(elapsed // 60)
        s = elapsed % 60
        return f"{m}m {s:.1f}s"
    return f"{elapsed:.1f}s"


class _ThinkingStatus:
    """Live-renderable that updates elapsed time and token counts on every refresh."""

    def __init__(self) -> None:
        self._started_at = time.monotonic()
        self._phase: str = "up"
        self._tokens: int = 0

    def update(self, phase: str, tokens: int) -> None:
        self._phase = phase
        self._tokens = tokens

    def __rich_console__(self, console, options):
        elapsed = time.monotonic() - self._started_at
        frame = SPINNER_FRAMES[int(elapsed * 1000 / _SPINNER_MS) % len(SPINNER_FRAMES)]
        arrow = "↑" if self._phase == "up" else "↓"
        token_part = f"  {arrow}{self._tokens}" if self._tokens else ""
        stats = f"({elapsed:.1f}s{token_part})"

        yield Segment.line()
        yield Text.assemble((frame, "reagent.spinner_frame"), (f" thinking  {stats}", "dim"))


TERMINAL_THEME = Theme(
    {
        "reagent.assistant_bullet": "white",
        "reagent.think": "dim italic",
        "reagent.tool_bullet": "green",
        "reagent.tool_call": "bold",
        "reagent.guide": "dim",
        "reagent.success": "green",
        "reagent.error": "red",
        "reagent.spinner_frame": "light_slate_blue",
        "reagent.status": "yellow",
        "reagent.prompt": "cyan",
        "reagent.user": "grey100 on #554d57",
        "reagent.user_prefix": "grey70 on #554d57",
    }
)

ASSISTANT_BULLET_STYLE = Style.parse("white")
TOOL_BULLET_STYLE = Style.parse("green")
GUIDE_STYLE = Style.parse("dim")
USER_STYLE = Style.parse("grey100 on #554d57")
USER_PREFIX_STYLE = Style.parse("grey70 on #554d57")
_BG_ADD = Style.parse("on #213A2B")  # dark green bg for diff additions (codex palette)
_BG_DEL = Style.parse("on #4A221D")  # dark red bg for diff deletions (codex palette)
_EDITOR_INDENT = "     "  # left margin for read/diff editor lines


def _display_directory(path: Path) -> str:
    home = Path.home()
    try:
        relative = path.relative_to(home)
        prefix = "~"
    except ValueError:
        relative = path
        prefix = ""

    parts = relative.parts
    if len(parts) > 3:
        directory = str(Path(parts[0], "…", *parts[-2:]))
    else:
        directory = str(relative) if parts else ""

    return f"{prefix}/{directory}" if prefix and directory else prefix or directory


def _progress_bar(*, used: int, limit: int, width: int = 20) -> Text:
    used_pct = min(1.0, used / limit) if limit else 0
    filled = round(used_pct * width)

    bar = Text()
    bar.append("█" * filled)
    bar.append("░" * (width - filled), style="dim")
    return bar


def _role_counts(session: Session) -> str:
    counts = Counter(m["role"] for m in session.messages)
    return f"{len(session.messages):,}  user={counts['user']:,}  assistant={counts['assistant']:,}  tool={counts['tool']:,}"


class RichRenderer:
    def __init__(self, console: Console | None = None, max_lines: int = 40, use_live: bool = True) -> None:
        self.console = console if console is not None else Console(theme=TERMINAL_THEME)
        self.max_lines = max_lines
        self._use_live = use_live
        self._live: Live | None = None
        self._thinking_status: _ThinkingStatus | None = None

    def startup_banner(self, model: str) -> None:
        directory = _display_directory(Path.cwd())

        title = Text.assemble(
            (">_ ", "dim"),
            ("REAgent", "white"),
            (f" v{_client_version()}", "dim"),
        )
        body = Group(
            title,
            Text(),
            Text.assemble(("model:", "dim"), "     ", model),
            Text.assemble(("directory:", "dim"), " ", directory),
        )

        self.console.print(Panel(body, box=rich_box.ROUNDED, border_style="dim", padding=(0, 1), expand=False))
        self.console.print()

    def assistant(self, text: str) -> None:
        if not text:
            return

        self.console.print()

        try:
            rendered = self.console.render_lines(
                Markdown(text), self.console.options.update(width=max(20, self.console.width - 2))
            )
            for index, line in enumerate(rendered):
                prefix = "• " if index == 0 else "  "
                self.console.print(
                    Segments([Segment(prefix, ASSISTANT_BULLET_STYLE), *self._rstrip_segments(line), Segment.line()])
                )
        except Exception:
            self._print_hanging_lines(text.splitlines(), bullet_style=ASSISTANT_BULLET_STYLE, content_style="")

    def think(self, text: str) -> None:
        if not text:
            return

        self.console.print()
        self._print_hanging_lines(text.splitlines(), bullet_style=GUIDE_STYLE, content_style="reagent.think")

    def tool_call(
        self,
        name: str,
        args: dict[str, Any],
        *,
        tool_call_id: str = "",
        bullet_style: Style = TOOL_BULLET_STYLE,
    ) -> None:
        del tool_call_id
        self.console.print()

        if name == "shell" and isinstance(args.get("command"), str):
            self._shell_call(args["command"], bullet_style=bullet_style)
            return

        formatted_args = self._fmt_args(name, args)
        lines = self._wrap_call(name, formatted_args)
        self._call_lines(lines, bullet_style=bullet_style)

    def tool_result(self, tool_call_id: str, result: ToolResult) -> None:
        del tool_call_id
        match result:
            case ErrorResult(message=msg):
                self._print_tree(self._clip_lines(_strip_ansi(msg)), style="reagent.error")
            case ShellResult(output=output):
                self._print_tree(self._clip_lines(_strip_ansi(output)), style="reagent.guide")
            case ReadResult(content=content, path=path, start_line=start_line):
                if content:
                    n = len(content.splitlines())
                    self._print_header(Text(f"Read {n} lines"))
                    self._print_read(content, path, start_line)
                else:
                    self._print_tree(["(empty file)"], style="reagent.guide")
            case DiffResult(diff=diff, path=path, message=msg, kind=kind):
                if diff:
                    raw_lines = diff.splitlines()
                    added = sum(1 for ln in raw_lines if ln.startswith("+") and not ln.startswith("+++"))
                    removed = sum(1 for ln in raw_lines if ln.startswith("-") and not ln.startswith("---"))
                    if kind == "write":
                        filename = Path(path).name
                        summary: Text = Text(f"Wrote {filename}  +{added}  -{removed}")
                    else:
                        summary = Text(f"Added {added}, removed {removed}")
                    self._print_header(summary)
                    self._print_diff(diff, path)
                else:
                    self._print_tree([msg], style="reagent.success")

    def _print_read(self, content: str, path: str, start_line: int) -> None:
        lines = content.splitlines()
        total = len(lines)
        if total > self.max_lines:
            lines = lines[: self.max_lines]

        num_w = len(str(start_line + len(lines) - 1))
        ext = Path(path).suffix.lstrip(".")
        inner_width = max(20, self.console.width - (len(_EDITOR_INDENT) + 3 + num_w))
        syntax = Syntax(
            "\n".join(lines),
            ext or "text",
            theme="ansi_dark",
            background_color="default",
            padding=(0, 0),
        )
        rendered = self.console.render_lines(syntax, self.console.options.update(width=inner_width))

        for i, seg_line in enumerate(rendered):
            ln = start_line + i
            self.console.print(
                Segments(
                    [
                        Segment(_EDITOR_INDENT, GUIDE_STYLE),
                        Segment(f" {ln:>{num_w}}", GUIDE_STYLE),
                        Segment("  "),
                        *self._rstrip_segments(seg_line),
                        Segment.line(),
                    ]
                )
            )

        if total > self.max_lines:
            self.console.print(Text(f"{_EDITOR_INDENT}... +{total - self.max_lines} lines omitted", style="dim"))

    def _print_diff(self, unified_diff: str, path: str) -> None:
        old_ln = new_ln = 0
        printed = 0
        total = 0

        parsed: list[tuple[int, str, str, str]] = []  # (ln, marker, content, status)
        hunk_starts: set[int] = set()
        for raw in unified_diff.splitlines():
            if raw.startswith(("---", "+++")):
                continue
            if raw.startswith("@@"):
                m = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
                if m:
                    old_ln = int(m.group(1))
                    new_ln = int(m.group(2))
                if parsed:
                    hunk_starts.add(len(parsed))
                continue
            if raw.startswith("+"):
                ln, marker, status = new_ln, "+", "add"
                new_ln += 1
            elif raw.startswith("-"):
                ln, marker, status = old_ln, "-", "del"
                old_ln += 1
            else:
                ln, marker, status = new_ln, " ", "ctx"
                old_ln += 1
                new_ln += 1
            total += 1
            if printed < self.max_lines:
                parsed.append((ln, marker, raw[1:], status))
                printed += 1

        if not parsed:
            return

        num_w = len(str(max(ln for ln, _, _, _ in parsed)))
        ext = Path(path).suffix.lstrip(".")
        inner_width = max(20, self.console.width - (len(_EDITOR_INDENT) + 3 + num_w))
        syntax = Syntax(
            "\n".join(c for _, _, c, _ in parsed),
            ext or "text",
            theme="ansi_dark",
            background_color="default",
            padding=(0, 0),
        )
        rendered = self.console.render_lines(syntax, self.console.options.update(width=inner_width))

        for i, ((ln, marker, _, status), seg_line) in enumerate(zip(parsed, rendered)):
            if i in hunk_starts:
                self.console.print(Text(_EDITOR_INDENT + " " * num_w + "⋮", style="dim"))

            if status == "add":
                marker_style = Style.parse("green")
                overlay: Style | None = _BG_ADD
            elif status == "del":
                marker_style = Style.parse("red")
                overlay = _BG_DEL + Style(dim=True)
            else:
                marker_style = GUIDE_STYLE
                overlay = None

            if overlay is not None:
                num_seg = Segment(f" {ln:>{num_w}}", GUIDE_STYLE + overlay)
                marker_seg = Segment(marker, marker_style + overlay)
                # keep trailing spaces so bg fills to inner_width; don't rstrip
                content_segs = [Segment(s.text, (s.style or Style()) + overlay) for s in seg_line]
                gutter_segs = [num_seg, marker_seg, Segment(" ", overlay)]
            else:
                content_segs = self._rstrip_segments(seg_line)
                gutter_segs = [Segment(f" {ln:>{num_w}}", GUIDE_STYLE), Segment(marker, marker_style), Segment(" ")]
            self.console.print(
                Segments(
                    [
                        Segment(_EDITOR_INDENT, GUIDE_STYLE),
                        *gutter_segs,
                        *content_segs,
                        Segment.line(),
                    ]
                )
            )

        if total > self.max_lines:
            self.console.print(Text(f"{_EDITOR_INDENT}... +{total - self.max_lines} lines omitted", style="dim"))

    def user(self, text: str) -> None:
        if not text:
            return
        self.console.print()
        width = self.console.width
        for index, line in enumerate(text.splitlines() or [""]):
            prefix = "> " if index == 0 else "  "
            padding = " " * max(0, width - len(prefix) - len(line))
            self.console.print(
                Segments(
                    [
                        Segment(prefix, USER_PREFIX_STYLE),
                        Segment(line, USER_STYLE),
                        Segment(padding, USER_STYLE),
                        Segment.line(),
                    ]
                )
            )

    def status(self, msg: str) -> None:
        self.console.print()
        self.console.print(Text(msg, style="reagent.status"))

    def notice(self, text: str) -> None:
        if not text:
            return
        self.console.print()
        self._print_hanging_lines(text.splitlines() or [""], bullet_style=GUIDE_STYLE, content_style="dim")

    def error(self, text: str) -> None:
        if not text:
            return
        self.console.print()
        self._print_hanging_lines(
            self._clip_lines(text), bullet_style=Style.parse("red"), content_style="reagent.error"
        )

    def status_panel(self, session: Session, config: Config) -> None:
        ctx = session.context_tokens
        limit = session.token_limit
        left = max(0, limit - ctx)
        left_pct = left / limit * 100 if limit else 0

        context = _progress_bar(used=ctx, limit=limit)
        context.append(f"  {left_pct:.0f}% left ({ctx:,} used / {limit:,})")
        if session.is_compacted:
            context.append("  compacted", style="dim")

        cached = f"  cached={session.cached_tokens:,}" if session.cached_tokens else ""
        reasoning = f"  reasoning={session.reasoning_tokens:,}" if session.reasoning_tokens else ""
        usage = (
            f"{session.total_tokens:,} total  input={session.prompt_tokens:,}  "
            f"output={session.completion_tokens:,}{cached}{reasoning}"
        )

        recorder = getattr(session, "_recorder", None)
        session_id = getattr(recorder, "session_id", None) or "none"
        session_path = getattr(recorder, "path", None)
        model = config.llm.model

        grid = Table.grid(padding=(0, 1))
        grid.add_column(style="dim", no_wrap=True)
        grid.add_column()

        title = Text.assemble(
            (">_ ", "dim"),
            ("REAgent", "text"),
            (f" v{_client_version()}", "dim"),
        )
        grid.add_row(title, "")
        grid.add_row("", "")
        grid.add_row("Model", model)
        grid.add_row("Directory", _display_directory(Path.cwd()))
        grid.add_row("Session", str(session_id))
        if session_path is not None:
            grid.add_row("Session file", _display_directory(Path(session_path)))
        grid.add_row("", "")
        grid.add_row("Messages", _role_counts(session))

        grid.add_row(
            "Turns",
            f"{session.turns:,}  LLM calls={session.llm_calls:,}  tool calls={session.tool_calls:,}",
        )
        grid.add_row("Token usage", usage)
        grid.add_row("Context window", context)

        self.console.print()
        self.console.print(Panel(grid, box=rich_box.ROUNDED, border_style="dim", padding=(0, 1), expand=False))
        self.console.print()

    def prompt(self, text: str) -> None:
        self.console.print(Text(text, style="reagent.prompt"), end="")
        self.console.file.flush()

    def thinking_start(self) -> None:
        if not self._use_live:
            self._thinking_status = _ThinkingStatus()
            return
        if self._live is None:
            self._thinking_status = _ThinkingStatus()
            self._live = Live(
                self._thinking_status,
                console=self.console,
                refresh_per_second=10,
                transient=True,
            )
            self._live.start()

    def thinking_update(self, phase: str, tokens: int) -> None:
        if self._thinking_status is not None:
            self._thinking_status.update(phase, tokens)

    def thinking_stop(self) -> None:
        if self._thinking_status is None:
            return
        elapsed = time.monotonic() - self._thinking_status._started_at
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._thinking_status = None
        self.console.print(Text(f"• thinking for {_fmt_elapsed(elapsed)}", style="dim"))

    def _print_hanging_lines(self, lines: list[str], bullet_style: Style, content_style: str) -> None:
        if not lines:
            return

        for index, line in enumerate(lines):
            prefix = "• " if index == 0 else "  "
            self.console.print(Text.assemble((prefix, bullet_style), (line, content_style)))

    def _shell_call(self, command: str, *, bullet_style: Style) -> None:
        logical_lines = command.splitlines() or [""]
        indent = " " * len("• shell(")

        for index, logical_line in enumerate(logical_lines):
            is_first_logical = index == 0
            is_last_logical = index == len(logical_lines) - 1

            prefix_segments = (
                [Segment("• ", bullet_style), Segment("shell(")] if is_first_logical else [Segment(indent, GUIDE_STYLE)]
            )
            suffix_segments = [Segment(")")] if is_last_logical else []
            prefix_width = len("• shell(") if is_first_logical else len(indent)
            suffix_width = 1 if is_last_logical else 0

            width = max(20, self.console.width - prefix_width - suffix_width)
            syntax = Syntax(logical_line, "bash", theme="ansi_dark", background_color="default", word_wrap=True)
            rendered_lines = self.console.render_lines(syntax, self.console.options.update(width=width))

            for rendered_index, rendered_line in enumerate(rendered_lines):
                line_prefix = prefix_segments if rendered_index == 0 else [Segment(indent, GUIDE_STYLE)]
                line_suffix = suffix_segments if rendered_index == len(rendered_lines) - 1 else []

                self.console.print(
                    Segments(
                        [
                            *line_prefix,
                            *self._rstrip_segments(rendered_line),
                            *line_suffix,
                            Segment.line(),
                        ]
                    )
                )

    def _call_lines(self, lines: list[str], *, bullet_style: Style) -> None:
        first, *rest = lines
        self.console.print(Text.assemble(("•", bullet_style), " ", (first, "reagent.tool_call")))

        for line in rest:
            self.console.print(Text.assemble(("  ", "reagent.guide"), (line, "reagent.tool_call")))

    def _rstrip_segments(self, segments: list[Segment]) -> list[Segment]:
        stripped = list(segments)
        while stripped and not stripped[-1].text.rstrip():
            stripped.pop()

        if stripped:
            stripped[-1] = Segment(stripped[-1].text.rstrip(), stripped[-1].style)

        return stripped

    def _fmt_args(self, name: str, args: dict[str, Any]) -> str:
        if not args:
            return ""

        if name in {"write_file", "read_file", "edit_file"} and isinstance(args.get("path"), str):
            return self._fmt_file(args)

        try:
            return json.dumps(args, ensure_ascii=False)
        except TypeError:
            return repr(args)

    def _fmt_file(self, args: dict[str, Any]) -> str:
        path = args["path"]
        start = args.get("start_line")
        end = args.get("end_line")

        if isinstance(start, int) and isinstance(end, int):
            return f"{path} {start}:{end}"

        if isinstance(start, int):
            return f"{path} {start}:"

        if isinstance(end, int):
            return f"{path} :{end}"

        return path

    def _wrap_call(self, name: str, formatted_args: str) -> list[str]:
        logical_lines = formatted_args.splitlines() or [""]
        logical_lines[0] = f"{name}({logical_lines[0]}"
        logical_lines[-1] = f"{logical_lines[-1]})"

        first_width = max(20, self.console.width - 2)
        rest_width = max(20, self.console.width - 4)
        lines: list[str] = []

        for logical_line in logical_lines:
            width = first_width if not lines else rest_width
            if not logical_line:
                lines.append("")
                continue
            lines.extend(
                textwrap.wrap(
                    logical_line,
                    width=width,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )

        return lines or [f"{name}()"]

    def _clip_lines(self, content: str) -> list[str]:
        lines = content.splitlines()
        if len(lines) <= self.max_lines:
            return lines

        if self.max_lines < 3:
            return lines[: self.max_lines]

        head_count = max(1, self.max_lines // 2)
        tail_count = self.max_lines - head_count - 1
        omitted = len(lines) - head_count - tail_count

        return [*lines[:head_count], f"... +{omitted} lines omitted", *lines[-tail_count:]]

    def _print_header(self, text: Text) -> None:
        self.console.print(Text.assemble(("  ⎿  ", GUIDE_STYLE), text))

    def _print_tree(self, lines: list[str], style: str) -> None:
        if not lines:
            return

        wrapped_lines = self._wrap_lines(lines)
        first, *rest = wrapped_lines
        self.console.print(Text.assemble(("  ⎿ ", GUIDE_STYLE), (first, style)))

        for line in rest:
            self.console.print(Text.assemble(("    ", GUIDE_STYLE), (line, style)))

    def _wrap_lines(self, lines: list[str]) -> list[str]:
        width = max(20, self.console.width - 4)
        wrapped: list[str] = []

        for line in lines:
            if not line:
                wrapped.append("")
                continue

            wrapped.extend(
                textwrap.wrap(
                    line,
                    width=width,
                    break_long_words=True,
                    break_on_hyphens=False,
                )
            )

        return wrapped
