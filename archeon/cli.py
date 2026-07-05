"""Command-line interface for Archeon."""

from __future__ import annotations

import importlib
import logging
import os
import re
import sys
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Backend log suppression — MUST run before the `archeon.*` imports below, which
# pull in cognee. Cognee configures its logging at *import time*: a structlog
# console handler on the root logger (writing to stderr) whose threshold it reads
# from LOG_LEVEL. Setting these env vars here, before that import happens, is
# what stops the "Cognee 1.0 changes / Logging initialized / auth posture" banner
# from printing right before our Rich UI renders. _silence_backend_logs() (after
# the imports) is the runtime follow-up for logs emitted during remember()/
# recall(). Export LOG_LEVEL yourself to override.
# --------------------------------------------------------------------------- #
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ.setdefault("LITELLM_LOG", "ERROR")

# Windows consoles default to a legacy code page (e.g. cp1252) that cannot encode
# the Unicode glyphs the Rich UI uses (arrows like "→", chips, box glyphs). Rich's
# legacy-Windows renderer then raises UnicodeEncodeError mid-render (crashing
# `why`'s decision chain). Force UTF-8 output before any rendering so every glyph
# is safe; errors="replace" is a last-resort guard against exotic characters.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass

import typer
from rich.columns import Columns
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from archeon import __version__
from archeon import memory
from archeon.ingest_pipeline import resolve_github_slug, run_ingest
from archeon.lifecycle import (
    DeprecatedDecisionRule,
    InvalidVoteError,
    LifecycleOperationError,
    MissingSourceFileRule,
    NoIncomingEdgesRule,
    ZeroConfidenceRule,
    detect_orphan_nodes,
    generate_adr,
    handle_feedback,
    handle_file_deletion,
    lifecycle_status,
    load_decision_graph,
)
from archeon.query_engine import QueryResult, query_sync
from archeon.schema import ConfidenceTier, DecisionGraph, GraphNode
from archeon.utils import format_path


def _silence_backend_logs(level: int = logging.ERROR) -> None:
    """Force cognee and its noisy dependencies to `level` so the terminal stays clean.

    The env vars at the top of this module stop cognee's import-time banner; this
    raises the threshold on the already-created loggers and on the console handler
    cognee attaches to the root logger, so nothing below `level` leaks during a
    live remember()/recall() run either.
    """
    for name in (
        "cognee",
        "litellm",
        "LiteLLM",
        "httpx",
        "httpcore",
        "openai",
        "sqlalchemy",
        "sqlalchemy.engine",
        "dlt",
        "alembic",
    ):
        logging.getLogger(name).setLevel(level)
    # Cognee attaches its structlog console handler to the ROOT logger; raise
    # every root handler's threshold so sub-`level` records never render.
    for handler in logging.getLogger().handlers:
        handler.setLevel(level)


_silence_backend_logs()

app = typer.Typer(
    name="archeon",
    help="Archeon developer decision memory CLI.",
    no_args_is_help=True,
)
console = Console()

# Cap the number of orphan rows rendered so a large repo can't produce a
# thousand-line table; the count in the header still reflects the true total.
GAPS_ROW_LIMIT = 40


def _target_width() -> int:
    """Uniform render width so every command's panels and tables line up."""
    return max(console.width, 110)


def _report_console() -> Console:
    """A console wide enough for Archeon's panels/tables in non-TTY runs."""
    return Console(width=_target_width())


def _emit(renderable) -> None:
    """Single output path — every command renders through one sized console."""
    _report_console().print(renderable)


# Blocking cognee/LLM calls (recall/search) can stall on network or provider
# back-off (e.g. an unfunded key's 429 retry loop). Cap them so the CLI degrades
# to a graceful panel instead of hanging on camera. Daemon thread so a stuck call
# can't keep the process alive at exit.
DEFAULT_BACKEND_TIMEOUT = 20.0


def _run_with_timeout(func, *args, timeout: float = DEFAULT_BACKEND_TIMEOUT, **kwargs):
    """Run a blocking backend call on a daemon thread; raise TimeoutError past `timeout`."""
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller thread
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"backend call exceeded {timeout:.0f}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


PASTEL = {
    "border": "bright_black",
    "green": "green",
    "yellow": "yellow",
    "blue": "blue",
    "cyan": "cyan",
    "purple": "magenta",
    "red": "red",
    "gray": "bright_black",
    "text": "white",
    "panel": "#1b2430",
}

# One border-colour + badge vocabulary for every command's result/notice frame.
_TONE_BORDER = {"success": "green", "warning": "yellow", "error": "red", "info": "blue"}
_TONE_BADGE = {"success": "SUCCESS", "warning": "WARNING", "error": "FAILED", "info": "INFO"}


def _command_title(command: str, context: str) -> Text:
    """The single Archeon title format: ARCHEON <command>  ·  <context>."""
    return Text.assemble(
        ("ARCHEON ", f"bold {PASTEL['purple']}"),
        (command, f"bold {PASTEL['cyan']}"),
        (f"  ·  {context}", PASTEL["text"]),
    )


def _panel(
    body,
    *,
    command: str,
    context: str,
    subtitle: str | Text | None = None,
    border: str = PASTEL["border"],
) -> Panel:
    """The one panel frame shared by every command — same title/border/padding."""
    sub = Text(subtitle, style=PASTEL["gray"]) if isinstance(subtitle, str) else subtitle
    return Panel(body, title=_command_title(command, context), subtitle=sub, border_style=border, padding=(1, 2))


def _notice(command: str, context: str, message: str | Text, *, tone: str = "info") -> Panel:
    """A standard one-line result/error frame (used for empty-states and confirmations)."""
    line = Text()
    line.append_text(_status_badge(_TONE_BADGE[tone]))
    line.append("  ")
    if isinstance(message, str):
        line.append(message, style=PASTEL["text"])
    else:
        line.append_text(message)
    return _panel(line, command=command, context=context, border=_TONE_BORDER[tone])


@app.command()
def ingest(
    repo: Path = typer.Argument(
        ...,
        help="Path to the repository to ingest.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
    ),
    github: str | None = typer.Option(
        None,
        "--github",
        help="GitHub owner/repo slug for PR extraction (auto-detected from origin when omitted).",
    ),
    output_dir: Path = typer.Option(
        Path(".archeon/extracts"),
        "--output-dir",
        help="Directory for JSONL extracts and ingest state.",
    ),
    incremental: bool = typer.Option(
        False,
        "--incremental",
        help="Only ingest commits added since the last run.",
    ),
    extract_only: bool = typer.Option(
        False,
        "--extract-only",
        help="Write JSONL extracts without calling Cognee.",
    ),
    no_cognify: bool = typer.Option(
        False,
        "--no-cognify",
        help="Add to Cognee without running cognify (batch mode).",
    ),
) -> None:
    """Extract repository history and remember it in Cognee."""
    target_output = output_dir / repo.name
    result = run_ingest(
        repo,
        output_dir=target_output,
        github_slug=github,
        incremental=incremental,
        extract_only=extract_only,
        cognify=not no_cognify,
    )

    _emit(_ingest_report(repo, result, extract_only=extract_only))


@app.command()
def why(
    file: Path | None = typer.Argument(
        None,
        help="Path to the file to explain (omit when using --question).",
        exists=False,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    question: str | None = typer.Option(
        None,
        "--question",
        "-q",
        help="Ask a free-text question directly instead of explaining a file.",
    ),
    search_type: str | None = typer.Option(
        None,
        "--search-type",
        help="Override the Cognee search type used by the query engine.",
    ),
    top_k: int = typer.Option(
        10,
        "--top-k",
        help="Maximum number of memory chunks to recall.",
    ),
    timeout: float = typer.Option(
        DEFAULT_BACKEND_TIMEOUT,
        "--timeout",
        help="Seconds to wait for the memory backend before returning a gap.",
    ),
) -> None:
    """Explain why code exists (query engine — Member B).

    Pass a FILE to explain, or ask a free-text question with --question/-q.
    """
    if question:
        query_text = question
    elif file is not None:
        query_text = _file_to_question(file)
    else:
        _emit(
            _notice(
                "why",
                "Decision Lookup",
                'Provide a FILE to explain, or ask a question with --question/-q. '
                'Example: archeon why -q "Why did we replace Redis with PostgreSQL?"',
                tone="error",
            )
        )
        raise typer.Exit(code=1)

    try:
        result = _run_with_timeout(
            query_sync, query_text, search_type=search_type, top_k=top_k, timeout=timeout
        )
    except TimeoutError:
        result = QueryResult(
            question=query_text,
            answer=(
                f"Query timed out after {timeout:.0f}s waiting on the memory backend "
                "(Cognee/LLM). Check LLM_API_KEY quota/billing, or raise --timeout."
            ),
            confidence=ConfidenceTier.UNKNOWN,
        )
    _emit(_why_report(file, result))


@app.command()
def forget(
    file: Path = typer.Argument(
        ...,
        help="Path whose decision memory should be forgotten (e.g. a deleted file).",
        exists=False,
        file_okay=True,
        dir_okay=True,
        resolve_path=True,
    ),
    timeout: float = typer.Option(
        DEFAULT_BACKEND_TIMEOUT,
        "--timeout",
        help="Seconds to wait for the memory backend before giving up.",
    ),
) -> None:
    """Forget decision nodes tied to a removed file (lifecycle forget-on-delete)."""
    try:
        forgotten = _run_with_timeout(handle_file_deletion, str(file), timeout=timeout)
    except TimeoutError:
        _emit(
            _notice(
                "forget",
                format_path(file),
                f"Timed out after {timeout:.0f}s contacting memory; nothing forgotten. "
                "Check LLM_API_KEY quota/billing or raise --timeout.",
                tone="warning",
            )
        )
        raise typer.Exit(code=1)
    except LifecycleOperationError as exc:
        _emit(
            _notice(
                "forget",
                format_path(file),
                f"{exc} The installed Cognee runtime may not expose forget()/prune.delete(), "
                "or the backend is unreachable. Check `archeon status`.",
                tone="warning",
            )
        )
        raise typer.Exit(code=1)
    _emit(_forget_report(file, forgotten))


@app.command()
def feedback(
    node_id: str = typer.Argument(..., help="Graph node id to apply feedback to."),
    vote: str = typer.Argument(..., help="Feedback vote: up or down (also +/-)."),
) -> None:
    """Apply up/down feedback to a decision node (lifecycle improve-on-feedback)."""
    try:
        normalized = handle_feedback(node_id, vote)
    except InvalidVoteError as exc:
        _emit(_notice("feedback", node_id, str(exc), tone="error"))
        raise typer.Exit(code=1)
    except LifecycleOperationError as exc:
        _emit(
            _notice(
                "feedback",
                node_id,
                f"{exc} The installed Cognee runtime may not expose improve()/memify(), "
                "or the backend is unreachable. Check `archeon status` and LLM_API_KEY.",
                tone="warning",
            )
        )
        raise typer.Exit(code=1)
    _emit(_feedback_report(node_id, normalized))


@app.command()
def gaps(
    repo: str | None = typer.Option(
        None,
        "--repo",
        help="Only inspect a single repo's extracts (by folder name under the extracts dir).",
    ),
    extracts_dir: Path = typer.Option(
        Path(".archeon/extracts"),
        "--extracts-dir",
        help="Directory of JSONL extracts written by `archeon ingest`.",
    ),
    repo_root: Path | None = typer.Option(
        None,
        "--repo-root",
        help="Repository root; enables detection of decisions whose source file was deleted.",
    ),
) -> None:
    """List undocumented / orphaned decisions (lifecycle orphan detection)."""
    graph = load_decision_graph(extracts_dir, repo=repo)
    if not graph.all_nodes():
        message = Text("No ingested memory found under ")
        message.append_text(_link_text(format_path(extracts_dir), str(extracts_dir)))
        message.append(". Run ", style=PASTEL["text"])
        message.append("archeon ingest <repo>", style=f"bold {PASTEL['cyan']}")
        message.append(" first.", style=PASTEL["text"])
        _emit(_notice("gaps", "Undocumented Decisions", message, tone="warning"))
        raise typer.Exit()

    root = str(repo_root) if repo_root else None
    orphans = detect_orphan_nodes(graph, repo_root=root)
    _emit(_gaps_report(graph, orphans, repo_root))


@app.command()
def recover(
    decision_id: str = typer.Argument(
        ...,
        help="Decision/node id (from `archeon gaps`) to draft an ADR for.",
    ),
    repo: str | None = typer.Option(
        None, "--repo", help="Only inspect a single repo's extracts (by folder name)."
    ),
    extracts_dir: Path = typer.Option(
        Path(".archeon/extracts"),
        "--extracts-dir",
        help="Directory of JSONL extracts written by `archeon ingest`.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the ADR draft to this file instead of the terminal.",
    ),
) -> None:
    """Generate an ADR draft for a decision id (lifecycle ADR recovery)."""
    graph = load_decision_graph(extracts_dir, repo=repo)
    node = _find_node(graph, decision_id)
    if node is None:
        message = Text.assemble(
            ("No node found for id ", PASTEL["text"]),
            (repr(decision_id), f"bold {PASTEL['cyan']}"),
            (". Run ", PASTEL["text"]),
            ("archeon gaps", f"bold {PASTEL['cyan']}"),
            (" to list recoverable ids.", PASTEL["text"]),
        )
        _emit(_notice("recover", decision_id, message, tone="error"))
        raise typer.Exit(code=1)

    markdown = generate_adr(node)
    if output:
        output.write_text(markdown, encoding="utf-8")
        written = Text("ADR draft written to ")
        written.append_text(_link_text(format_path(output), str(output)))
        _emit(_notice("recover", getattr(node, "title", None) or node.id, written, tone="success"))
    else:
        _emit(_adr_report(node, markdown, graph))


@app.command()
def status() -> None:
    """Show Archeon status."""
    state_root = Path(".archeon")
    state_files = list(state_root.glob("state/*.json")) if state_root.exists() else []
    extract_dirs = (
        [path for path in state_root.glob("extracts/*") if path.is_dir()]
        if state_root.exists()
        else []
    )
    lifecycle = lifecycle_status()

    _emit(_status_report(state_files, extract_dirs, lifecycle))


def _supports_unicode() -> bool:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in encoding


def _plain(value: int | str | None, fallback: str = "0") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _chip(label: str, bg: str, fg: str = "bright_white") -> Text:
    """A filled, reverse-video badge (colored background) for high scannability."""
    dot = "● " if _supports_unicode() else ""
    return Text(f" {dot}{label.upper()} ", style=f"bold {fg} on {bg}")


# Yellow backgrounds need dark text to stay legible.
_STATUS_BG = {
    "READY": "green",
    "SUCCESS": "green",
    "HEALTHY": "green",
    "CONNECTED": "green",
    "AVAILABLE": "green",
    "PENDING": "yellow",
    "WAITING": "yellow",
    "MISSING": "yellow",
    "NEEDS COGNEE": "yellow",
    "PLANNED": "blue",
    "UNKNOWN": "bright_black",
    "FAILED": "red",
}


def _status_badge(label: str) -> Text:
    normalized = label.upper()
    bg = _STATUS_BG.get(normalized, "blue")
    fg = "black" if bg == "yellow" else "bright_white"
    return _chip(normalized, bg, fg)


# Confidence tiers, most visual mapping: cited=green, inferred=yellow, gap=red.
_TIER_BG = {"CITED": "green", "INFERRED": "yellow", "UNKNOWN": "red"}


def _tier_color(label: str) -> str:
    return _TIER_BG.get(label.upper(), "blue")


def _confidence_badge(label: str) -> Text:
    normalized = label.upper()
    bg = _tier_color(normalized)
    fg = "black" if bg == "yellow" else "bright_white"
    return _chip(normalized, bg, fg)


def _section_heading(title: str, *, color: str) -> Text:
    marker = "✓ " if _supports_unicode() else "+ "
    return Text.assemble(
        (marker, f"bold {PASTEL['text']}"),
        (title, f"bold {color}"),
    )


def _link_text(display: str, path: str) -> Text:
    text = Text(display, style=f"underline {PASTEL['blue']}")
    candidate = Path(path)
    try:
        text.stylize(f"link {candidate.resolve().as_uri()}")
    except ValueError:
        pass
    return text


def _responsive_columns(*renderables) -> Columns | Group:
    if console.width < 110:
        spaced = []
        for renderable in renderables:
            if spaced:
                spaced.append(Text(" "))
            spaced.append(renderable)
        return Group(*spaced)
    return Columns(renderables, equal=True, expand=True)


def _file_to_question(file: Path) -> str:
    """Adapt a file path argument into a natural-language question.

    The query engine (Member B) answers free-text questions, not paths, so the
    CLI is responsible for phrasing one. We use both the bare name and the
    readable path so citations can match either form.
    """
    label = format_path(file)
    return (
        f"Why does {file.name} exist? What engineering decisions, tradeoffs, "
        f"rejected alternatives, and consequences explain the code in {label}?"
    )


_CONFIDENCE_BASIS = {
    ConfidenceTier.CITED: "Backed by explicit commit, PR, issue, ADR, or README evidence.",
    ConfidenceTier.INFERRED: "Derived from recalled context without an attributable source.",
    ConfidenceTier.UNKNOWN: "No supporting evidence recovered; treat as a memory gap.",
}

_SUMMARY_BY_TIER = {
    ConfidenceTier.CITED: "Answer is backed by cited engineering evidence; see EVIDENCE above.",
    ConfidenceTier.INFERRED: "Answer is inferred from recalled context; no direct citation was recovered.",
    ConfidenceTier.UNKNOWN: "No cited engineering rationale is available for this target yet.",
}


@lru_cache(maxsize=8)
def _github_slug(root: str) -> str | None:
    """Best-effort owner/repo for the current checkout (cached; read-only)."""
    try:
        return resolve_github_slug(Path(root), None)
    except Exception:  # noqa: BLE001 - links are optional polish, never fatal
        return None


def _github_url(source_type: str, locator: str) -> str | None:
    """Build a canonical GitHub URL for a PR / issue / commit locator, if we can."""
    slug = _github_slug(str(Path.cwd()))
    if not slug or not locator:
        return None
    loc = locator.strip()
    if source_type == "pull_request":
        num = loc.lstrip("PR-").lstrip("#")
        return f"https://github.com/{slug}/pull/{num}" if num.isdigit() else None
    if source_type == "issue":
        num = loc.lstrip("#")
        return f"https://github.com/{slug}/issues/{num}" if num.isdigit() else None
    if source_type == "commit" and re.fullmatch(r"[0-9a-fA-F]{7,40}", loc):
        return f"https://github.com/{slug}/commit/{loc}"
    return None


def _dash() -> str:
    return "—" if _supports_unicode() else "-"


def _source_link(source_type: str, locator: str | None) -> Text:
    """Render a locator as a clickable link (file:// or GitHub) or distinct cyan."""
    if not locator:
        return Text(_dash(), style=PASTEL["gray"])
    if _looks_like_path(locator):
        return _link_text(locator, locator)
    text = Text(locator, style=f"bold {PASTEL['cyan']}")
    url = _github_url(source_type, locator)
    if url:
        text.stylize(f"link {url}")
    return text


# Ordering + display labels for the decision chain (issue -> PR -> commit -> ...).
_CHAIN_ORDER = ["issue", "pull_request", "commit", "adr", "readme", "doc", "session_log", "other"]
_CHAIN_LABEL = {
    "issue": "Issue",
    "pull_request": "Pull Request",
    "commit": "Commit",
    "adr": "ADR",
    "readme": "README",
    "doc": "Doc",
    "session_log": "Session log",
    "other": "Source",
}


def _chain_rank(source_type: str) -> int:
    return _CHAIN_ORDER.index(source_type) if source_type in _CHAIN_ORDER else len(_CHAIN_ORDER)


def _why_chain_tree(result: QueryResult) -> Tree:
    """Nest cited sources into a flow tree so the reasoning path reads top-down."""
    root = Tree(Text("Decision chain  (issue → PR → commit)", style=f"bold {PASTEL['purple']}"))
    ordered = sorted(result.sources, key=lambda s: _chain_rank(s.source_type.value))
    if not ordered:
        root.add(
            Text(
                "No linked evidence yet — the chain appears once sources are cited.",
                style=PASTEL["gray"],
            )
        )
        return root

    cursor = root
    for src in ordered:
        stype = src.source_type.value
        label = Text(f"{_CHAIN_LABEL.get(stype, stype)}  ", style=f"bold {PASTEL['text']}")
        label.append_text(_source_link(stype, src.locator))
        if src.snippet:
            label.append(f"  {src.snippet.strip().splitlines()[0][:70]}", style=PASTEL["gray"])
        cursor = cursor.add(label)  # nest under the previous step to show the cascade
    return root


def _evidence_table(file: Path | None, result: QueryResult) -> Table:
    table = Table(box=None, expand=True, padding=(0, 2))
    table.add_column("Type", width=14, style=f"bold {PASTEL['gray']}", no_wrap=True)
    table.add_column("Reference", width=24, no_wrap=True, overflow="ellipsis")
    table.add_column("Explanation", ratio=4, style=PASTEL["gray"], overflow="fold")
    if file is not None:
        table.add_row(
            "File",
            _link_text(format_path(file), str(file)),
            Text("Target file for the decision question.", style=PASTEL["gray"]),
        )
    if result.sources:
        for src in result.sources:
            stype = src.source_type.value
            table.add_row(
                Text(_CHAIN_LABEL.get(stype, stype), style=f"bold {PASTEL['gray']}"),
                _source_link(stype, src.locator),
                Text(src.snippet.strip()[:160] if src.snippet else "(no snippet)", style=PASTEL["gray"]),
            )
    else:
        table.add_row(
            "Citation",
            _confidence_badge("unknown"),
            Text("No supporting PR, commit, ADR, or README citation was recovered.", style=PASTEL["gray"]),
        )
    return table


def _confidence_line(tier: ConfidenceTier) -> Text:
    line = Text()
    line.append_text(_confidence_badge(tier.value))
    line.append(f"  {_CONFIDENCE_BASIS[tier]}", style=PASTEL["gray"])
    return line


def _question_label(question: str, limit: int = 60) -> str:
    """Short, single-line label for a free-text question (panel title/context)."""
    collapsed = " ".join(question.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 3] + "..."


def _why_report(file: Path | None, result: QueryResult) -> Panel:
    tier = result.confidence
    body = Group(
        _section_heading("DECISION", color=PASTEL["purple"]),
        Text(result.answer, style=PASTEL["text"]),
        Text(""),
        _section_heading("CONFIDENCE", color=PASTEL["purple"]),
        _confidence_line(tier),
        Text(""),
        _section_heading("DECISION CHAIN", color=PASTEL["purple"]),
        _why_chain_tree(result),
        Text(""),
        _section_heading("EVIDENCE", color=PASTEL["purple"]),
        _evidence_table(file, result),
        Text(""),
        Text(_SUMMARY_BY_TIER[tier], style=PASTEL["gray"]),
    )

    subtitle = Text("confidence ", style=PASTEL["gray"])
    subtitle.append_text(_confidence_badge(tier.value))
    context = format_path(file) if file is not None else _question_label(result.question)
    return _panel(
        body,
        command="why",
        context=context,
        subtitle=subtitle,
        border=_tier_color(tier.value),
    )


def _looks_like_path(locator: str) -> bool:
    return "/" in locator or "\\" in locator or bool(Path(locator).suffix)


# --------------------------------------------------------------------------- #
# Lifecycle: gaps / recover rendering (routing + formatting stays in the CLI)
# --------------------------------------------------------------------------- #


def _find_node(graph: DecisionGraph, decision_id: str) -> GraphNode | None:
    """Resolve a node by exact id, then by id suffix or locator (convenience)."""
    index = graph.node_index()
    if decision_id in index:
        return index[decision_id]
    for node in graph.all_nodes():
        if node.id.endswith(decision_id) or getattr(node, "locator", None) == decision_id:
            return node
    return None


def _gap_reasons(node: GraphNode, graph: DecisionGraph, repo_root: Path | None) -> str:
    """Explain why a node was flagged, reusing the backend orphan rules for display."""
    checks = [
        (ZeroConfidenceRule(), "unknown confidence"),
        (NoIncomingEdgesRule(), "no incoming edges"),
        (DeprecatedDecisionRule(), "decision deprecated"),
    ]
    if repo_root is not None:
        checks.append((MissingSourceFileRule(repo_root), "source file missing on disk"))
    reasons = [label for rule, label in checks if rule.is_orphan(node, graph)]
    return ", ".join(reasons) or "flagged by orphan rules"


def _gaps_report(
    graph: DecisionGraph,
    orphans: list[GraphNode],
    repo_root: Path | None,
) -> Panel:
    total = len(graph.all_nodes())

    if not orphans:
        body: Group | Text = Text(
            f"No gaps found across {total} reconstructed node(s). "
            "Every decision in memory is documented and connected.",
            style=PASTEL["green"],
        )
        border = "green"
    else:
        table = Table(box=None, expand=True, padding=(0, 1))
        table.add_column("Type", width=9, style=f"bold {PASTEL['gray']}", no_wrap=True)
        table.add_column("Id", width=26, style=PASTEL["cyan"], no_wrap=True, overflow="ellipsis")
        table.add_column("Confidence", width=13, no_wrap=True)
        table.add_column("Reason", width=22, style=PASTEL["yellow"], overflow="fold")
        table.add_column("Source / summary", ratio=1, overflow="fold")
        for node in orphans[:GAPS_ROW_LIMIT]:
            confidence = getattr(node, "confidence", None)
            conf_cell = (
                _confidence_badge(confidence.value)
                if confidence is not None
                else Text("n/a", style=PASTEL["gray"])
            )
            path = getattr(node, "path", None)
            if path:
                source_cell: Text = _link_text(path, path)
            else:
                first = node.text.strip().splitlines()[0][:100] if node.text.strip() else "(no text)"
                source_cell = Text(first, style=PASTEL["gray"])
            table.add_row(
                node.type.value,
                node.id,
                conf_cell,
                _gap_reasons(node, graph, repo_root),
                source_cell,
            )

        rows: list = [table]
        if len(orphans) > GAPS_ROW_LIMIT:
            rows.append(Text(f"... and {len(orphans) - GAPS_ROW_LIMIT} more", style=PASTEL["gray"]))
        rows.append(Text(""))
        rows.append(Text("Recover an ADR draft with:  archeon recover <id>", style=PASTEL["gray"]))
        body = Group(*rows)
        border = "red"

    return _panel(
        body,
        command="gaps",
        context="Undocumented Decisions",
        subtitle=f"{len(orphans)}/{total} flagged",
        border=border,
    )


def _decision_chain_tree(node: GraphNode, graph: DecisionGraph) -> Tree:
    """Walk the reconstructed graph edges into an Evidence → Decision → Files tree."""
    index = graph.node_index()
    title = getattr(node, "title", None) or node.text.strip().splitlines()[0][:60]
    root = Tree(
        Text.assemble((f"{node.type.value}: ", f"bold {PASTEL['purple']}"), (title, PASTEL["text"]))
    )

    evidence_ids = [e.source_id for e in graph.edges if e.type.value == "CITED_IN" and e.target_id == node.id]
    file_ids = [e.target_id for e in graph.edges if e.type.value == "AFFECTS_FILE" and e.source_id == node.id]

    if evidence_ids:
        branch = root.add(Text("Evidence", style=f"bold {PASTEL['cyan']}"))
        for eid in evidence_ids:
            ev = index.get(eid)
            if ev is None:
                continue
            source_type = getattr(ev, "source_type", None)
            branch.add(_source_link(source_type.value if source_type else "other", getattr(ev, "locator", None)))
    if file_ids:
        branch = root.add(Text("Affected files", style=f"bold {PASTEL['cyan']}"))
        for fid in file_ids:
            code_file = index.get(fid)
            if code_file is None:
                continue
            branch.add(_source_link("other", getattr(code_file, "path", None) or code_file.id))
    if not evidence_ids and not file_ids:
        root.add(Text("No linked evidence or files in the reconstructed graph.", style=PASTEL["gray"]))
    return root


def _adr_report(node: GraphNode, markdown: str, graph: DecisionGraph) -> Panel:
    meta = Table(box=None, expand=True, padding=(0, 2), show_header=False)
    meta.add_column("Field", width=14, style=f"bold {PASTEL['gray']}", no_wrap=True)
    meta.add_column("Value", ratio=4, style=PASTEL["text"], overflow="fold")
    meta.add_row("Node id", Text(node.id, style=PASTEL["cyan"]))
    confidence = getattr(node, "confidence", None)
    if confidence is not None:
        meta.add_row("Confidence", _confidence_badge(confidence.value))

    adr_panel = Panel(
        Markdown(markdown),
        title=Text("ADR DRAFT", style=f"bold {PASTEL['purple']}"),
        border_style=PASTEL["blue"],
        padding=(1, 2),
    )

    body = Group(
        _section_heading("SOURCE NODE", color=PASTEL["purple"]),
        meta,
        Text(""),
        _section_heading("DECISION CHAIN", color=PASTEL["purple"]),
        _decision_chain_tree(node, graph),
        Text(""),
        adr_panel,
    )
    return _panel(
        body,
        command="recover",
        context=getattr(node, "title", None) or node.type.value,
        subtitle="ADR recovery",
        border="green",
    )


def _ingest_report(repo: Path, result: Any, *, extract_only: bool) -> Panel:
    metrics = Table(box=None, expand=True, padding=(0, 2), show_header=False)
    metrics.add_column("Metric", width=20, style=f"bold {PASTEL['gray']}", no_wrap=True)
    metrics.add_column("Value", ratio=1, style=PASTEL["text"], overflow="fold")
    metrics.add_row("Records extracted", _plain(result.records_extracted))
    metrics.add_row("Chunks prepared", _plain(result.chunks_prepared))
    if result.skipped_incremental:
        metrics.add_row("Skipped (known)", _plain(result.skipped_incremental))
    if result.cognee_used:
        metrics.add_row("Remembered", f"{result.chunks_remembered} chunk(s) in Cognee")
    if result.jsonl_paths:
        last = result.jsonl_paths[-1]
        metrics.add_row("JSONL output", _link_text(format_path(last), str(last)))

    sources = Table(box=None, expand=True, padding=(0, 2), show_header=False)
    sources.add_column("Source", width=20, style=f"bold {PASTEL['gray']}", no_wrap=True)
    sources.add_column("Records", justify="right", style=PASTEL["cyan"], no_wrap=True)
    for source, count in sorted(result.source_counts.items()):
        sources.add_row(source, _plain(count))
    sources_block: Table | Text = (
        sources if result.source_counts else Text("No source records extracted.", style=PASTEL["gray"])
    )

    if extract_only:
        badge, message, border = "success", "Extracts written; Cognee remember skipped (--extract-only).", "green"
    elif result.cognee_used:
        badge, message, border = "success", f"Remembered {result.chunks_remembered} chunk(s) in Cognee.", "green"
    elif not memory.cognee_available():
        badge, message, border = (
            "needs cognee",
            "Cognee not installed — JSONL written. `pip install -e .[cognee]` to remember.",
            "yellow",
        )
    elif result.chunks_prepared == 0:
        badge, message, border = "missing", "No records found to remember.", "yellow"
    else:
        badge, message, border = "success", "Ingest complete.", "green"

    status_line = Text()
    status_line.append_text(_status_badge(badge))
    status_line.append(f"  {message}", style=PASTEL["text"])

    body = Group(
        _section_heading("INGEST SUMMARY", color=PASTEL["purple"]),
        metrics,
        Text(""),
        _section_heading("SOURCES", color=PASTEL["purple"]),
        sources_block,
        Text(""),
        status_line,
    )
    subtitle = f"{result.records_extracted} records · {result.chunks_prepared} chunks"
    return _panel(body, command="ingest", context=format_path(repo), subtitle=subtitle, border=border)


def _forget_report(file: Path, forgotten: list[str]) -> Panel:
    if forgotten:
        line = Text()
        line.append_text(_status_badge("success"))
        line.append(f"  Forgot {len(forgotten)} node(s) tied to {format_path(file)}.", style=PASTEL["text"])
        table = Table(box=None, expand=True, padding=(0, 1), show_header=False)
        table.add_column("Forgotten node", ratio=1, style=PASTEL["cyan"], overflow="fold")
        for node_id in forgotten:
            table.add_row(node_id)
        body: Group | Text = Group(
            line,
            Text(""),
            _section_heading("FORGOTTEN NODES", color=PASTEL["purple"]),
            table,
        )
        border = "green"
    else:
        line = Text()
        line.append_text(_status_badge("missing"))
        line.append(
            f"  No matching decision nodes were found to forget for {format_path(file)}.",
            style=PASTEL["text"],
        )
        body = line
        border = "yellow"
    return _panel(body, command="forget", context=format_path(file), border=border)


def _feedback_report(node_id: str, vote: str) -> Panel:
    bg = "green" if vote == "up" else "yellow"
    fg = "black" if bg == "yellow" else "bright_white"
    line = Text("Recorded ", style=PASTEL["text"])
    line.append_text(_chip(vote, bg, fg))
    line.append("  feedback for ", style=PASTEL["text"])
    line.append(node_id, style=PASTEL["cyan"])
    body = Group(_section_heading("FEEDBACK", color=PASTEL["purple"]), line)
    return _panel(body, command="feedback", context=node_id, subtitle="improve-on-feedback", border=bg)


def _status_report(
    state_files: list[Path],
    extract_dirs: list[Path],
    lifecycle: dict,
) -> Panel:
    body = Group(
        _system_status_panel(),
        Text(""),
        _decision_summary_panel(),
        Text(""),
        _evidence_panel(state_files, extract_dirs),
        Text(""),
        _lifecycle_panel(lifecycle),
    )
    return _panel(
        body,
        command="status",
        context="Developer Decision Memory, Powered by Cognee",
        subtitle=f"v{__version__}  ·  Health and System Overview",
    )


def _system_status_panel() -> Group:
    if memory.cognee_available():
        cognee_badge = _status_badge("available")
        cognee_message = "Memory backend is connected and ready."
        cognee_next = "Run ingest to capture fresh project decisions."
    else:
        cognee_badge = _status_badge("missing")
        cognee_message = "Memory backend is not available yet."
        cognee_next = "Install dependencies to enable memory persistence."

    status_table = Table(box=None, show_header=True, expand=True, padding=(0, 2))
    status_table.add_column("Component", width=14, style=f"bold {PASTEL['gray']}", no_wrap=True)
    status_table.add_column("Current state", width=15, no_wrap=True)
    status_table.add_column("Description", ratio=2, style=PASTEL["gray"], overflow="fold")
    status_table.add_column("Next Action", ratio=2, style=PASTEL["gray"], overflow="fold")
    status_table.add_row(
        "CLI",
        _status_badge("ready"),
        "Command surface is available.",
        "Use status for health checks and why for decision lookup.",
    )
    status_table.add_row(
        "Cognee",
        cognee_badge,
        cognee_message,
        cognee_next,
    )
    status_table.add_row(
        "Query Engine",
        _status_badge("ready"),
        "Decision explanation engine is wired into `archeon why`.",
        "Run why <file> to recall cited rationale from memory.",
    )

    return Group(
        _section_heading("SYSTEM STATUS", color=PASTEL["purple"]),
        status_table,
    )


def _decision_summary_panel() -> Group:
    return Group(
        _section_heading("DECISION SUMMARY", color=PASTEL["purple"]),
        _responsive_columns(_decision_chain_section(), _confidence_section()),
    )


def _decision_chain_section() -> Group:
    chain = Group(
        _chain_step(
            "1. Extract",
            "ready",
            "Git, PRs, README, docs, and demo fixtures",
            label_color=PASTEL["gray"],
            detail_color=PASTEL["gray"],
        ),
        _chain_step(
            "2. Remember",
            "available" if memory.cognee_available() else "needs cognee",
            "Cognee memory wrapper",
            label_color=PASTEL["gray"],
            detail_color=PASTEL["gray"],
        ),
        _chain_step(
            "3. Recall",
            "ready",
            "Member B query engine (archeon why)",
            label_color=PASTEL["gray"],
            detail_color=PASTEL["gray"],
        ),
        _chain_step(
            "4. Cite",
            "planned",
            "Commit and PR source links in answer output",
            detail_color=PASTEL["gray"],
            label_color=PASTEL["gray"],
        ),
    )

    note = Text("Core reasoning path: Decision, Context, Consequence, File", style=PASTEL["gray"])
    return Group(
        Text("Decision Flow", style=f"bold {PASTEL['text']}"),
        chain,
        note,
    )


def _chain_step(
    label: str,
    status_label: str,
    detail: str,
    *,
    label_color: str = PASTEL["text"],
    detail_color: str = PASTEL["text"],
) -> Text:
    return Text.assemble(
        (f"{label:<12}", label_color),
        _status_badge(status_label),
        (f"  {detail}", detail_color),
    )


def _evidence_panel(state_files: list[Path], extract_dirs: list[Path]) -> Group:
    return Group(
        _section_heading("MEMORY SOURCES", color=PASTEL["purple"]),
        _responsive_columns(
            _ingest_workspace_section(state_files, extract_dirs),
            _source_links_section(),
        ),
    )


def _ingest_workspace_section(state_files: list[Path], extract_dirs: list[Path]) -> Group:
    table = Table(box=None, expand=True, padding=(0, 2), show_header=False)
    table.add_column("Artifact", width=16, style=f"bold {PASTEL['gray']}", no_wrap=True)
    table.add_column("Count", width=8, justify="right", style=f"bold {PASTEL['gray']}", no_wrap=True)
    table.add_column("Meaning", ratio=3, style=PASTEL["gray"], overflow="fold")
    table.add_row("State files", _plain(len(state_files)), "Incremental checkpoints")
    table.add_row("Extract dirs", _plain(len(extract_dirs)), "JSONL output folders")
    return Group(
        Text("Workspace Snapshot", style=f"bold {PASTEL['text']}"),
        table,
    )


def _confidence_section() -> Group:
    table = Table(box=None, expand=True, padding=(0, 2), show_header=False)
    table.add_column("Confidence", width=14, no_wrap=True)
    table.add_column("Meaning", ratio=3, style=PASTEL["gray"], overflow="fold")
    table.add_row(_confidence_badge("cited"), "Explicit commit, PR, issue, README, or ADR evidence")
    table.add_row(_confidence_badge("inferred"), "Derived from graph structure or code context")
    table.add_row(_confidence_badge("unknown"), "No supporting evidence; candidate for gaps/recover")
    return Group(
        Text("Confidence Guide", style=f"bold {PASTEL['text']}"),
        table,
    )


def _source_links_section() -> Group:
    table = Table(box=None, expand=True, padding=(0, 2))
    table.add_column("Source", width=18, style=f"bold {PASTEL['gray']}", no_wrap=True)
    table.add_column("Path", ratio=2, no_wrap=True, overflow="ellipsis")
    table.add_column("Evidence", ratio=3, style=PASTEL["text"], overflow="fold")
    table.add_row(
        Text("Commits", style=f"bold {PASTEL['gray']}"),
        _link_text("history/commits.jsonl", "demo/atlas-api/history/commits.jsonl"),
        Text("5 records with explicit why fields", style=PASTEL["gray"]),
    )
    table.add_row(
        Text("Pull requests", style=f"bold {PASTEL['gray']}"),
        _link_text("history/pull-requests.md", "demo/atlas-api/history/pull-requests.md"),
        Text("4 PRs with alternatives and tradeoffs", style=PASTEL["gray"]),
    )
    table.add_row(
        Text("ADRs", style=f"bold {PASTEL['gray']}"),
        _link_text("docs/architecture-decisions.md", "demo/atlas-api/docs/architecture-decisions.md"),
        Text("Redis/PostgreSQL and Flask/FastAPI chain", style=PASTEL["gray"]),
    )
    return Group(
        Text("Evidence Links", style=f"bold {PASTEL['text']}"),
        table,
    )


def _lifecycle_panel(lifecycle: dict) -> Group:
    rows = [
        ("Forgotten nodes", int(lifecycle.get("forgotten_count", 0)), "forget() pruning candidates"),
        ("Improved nodes", int(lifecycle.get("improved_count", 0)), "feedback-weighted memory"),
        ("Orphans", int(lifecycle.get("orphan_count", 0)), "future archeon gaps input"),
        ("ADR drafts", int(len(lifecycle.get("adr_drafts", []))), "future archeon recover output"),
    ]
    active = [row for row in rows if row[1] > 0]
    idle = [row for row in rows if row[1] == 0]

    table = Table(box=None, expand=True, padding=(0, 2), show_header=False)
    table.add_column("Signal", width=18, style=f"bold {PASTEL['text']}", no_wrap=True)
    table.add_column("Count", width=8, justify="right", style=f"bold {PASTEL['text']}", no_wrap=True)
    table.add_column("Use", ratio=3, style=PASTEL["text"], overflow="fold")

    for signal, count, meaning in active:
        table.add_row(signal, _plain(count), meaning)

    if not active:
        table.add_row("Lifecycle activity", _plain(0), Text("No active memory lifecycle signals yet.", style=PASTEL["gray"]))

    idle_names = ", ".join(signal for signal, _, _ in idle)

    return Group(
        _section_heading("MEMORY LIFECYCLE", color=PASTEL["purple"]),
        table,
        Text(f"Idle (0): {idle_names}", style=PASTEL["gray"]),
    )


def main() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    main()
