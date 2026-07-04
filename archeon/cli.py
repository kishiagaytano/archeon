"""Command-line interface for Archeon."""

from __future__ import annotations

from pathlib import Path

import typer

from archeon import memory
from archeon.ingest_pipeline import run_ingest
from archeon.query_engine import query_sync
from archeon.schema import ConfidenceTier
from archeon.utils import format_path

# Confidence badges for terminal output.
_CONFIDENCE_BADGE = {
    ConfidenceTier.CITED: "[cited]",
    ConfidenceTier.INFERRED: "[inferred]",
    ConfidenceTier.UNKNOWN: "[unknown]",
}

app = typer.Typer(
    name="archeon",
    help="Archeon developer decision memory CLI.",
    no_args_is_help=True,
)


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

    typer.echo(f"Ingested {format_path(repo)}")
    typer.echo(f"  records extracted: {result.records_extracted}")
    typer.echo(f"  chunks prepared:   {result.chunks_prepared}")
    if result.skipped_incremental:
        typer.echo(f"  skipped (known):   {result.skipped_incremental}")
    for source, count in sorted(result.source_counts.items()):
        typer.echo(f"  - {source}: {count}")

    if result.jsonl_paths:
        typer.echo(f"  jsonl output:      {format_path(result.jsonl_paths[-1])}")

    if extract_only:
        typer.echo("Cognee remember skipped (--extract-only).")
    elif result.cognee_used:
        typer.echo(f"  remembered:        {result.chunks_remembered} chunk(s) in Cognee")
    elif not memory.cognee_available():
        typer.echo(
            "Cognee is not installed. JSONL extracts were written; "
            "install with `pip install -e .[cognee]` to remember."
        )
    elif result.chunks_prepared == 0:
        typer.echo("No records found to remember.")


@app.command()
def why(
    target: str = typer.Argument(
        ...,
        help="A file path or a natural-language question about a decision.",
    ),
    top_k: int = typer.Option(10, help="How many memory chunks to consider."),
) -> None:
    """Explain why a file exists or a decision was made."""
    question = _as_question(target)
    result = query_sync(question, top_k=top_k)

    typer.echo(f"{_CONFIDENCE_BADGE[result.confidence]} {result.question}")
    typer.echo("")
    typer.echo(result.answer)

    if result.sources:
        typer.echo("")
        typer.echo("Sources:")
        for source in result.sources:
            locator = f" {source.locator}" if source.locator else ""
            typer.echo(f"  - {source.source_type.value}{locator}")


def _as_question(file_or_question: str) -> str:
    """Turn a bare file path into a 'why does X exist?' question."""
    if " " in file_or_question or "?" in file_or_question:
        return file_or_question
    return f"Why does {file_or_question} exist, and what decision shaped it?"


@app.command()
def status() -> None:
    """Show Archeon status."""
    typer.echo("Archeon CLI is ready.")
    if memory.cognee_available():
        typer.echo("Cognee integration: available")
    else:
        typer.echo("Cognee integration: not installed (pip install -e .[cognee])")
        if memory.import_error():
            typer.echo(f"  import error: {memory.import_error()!r}")

    state_root = Path(".archeon")
    if state_root.exists():
        state_files = list(state_root.glob("state/*.json"))
        if state_files:
            typer.echo(f"Ingest state files: {len(state_files)}")
        extract_dirs = [path for path in state_root.glob("extracts/*") if path.is_dir()]
        if extract_dirs:
            typer.echo(f"Extract directories: {len(extract_dirs)}")

    lifecycle = lifecycle_status()
    typer.echo("Lifecycle status:")
    typer.echo(f"  forgotten nodes: {lifecycle['forgotten_count']}")
    typer.echo(f"  improved nodes:  {lifecycle['improved_count']}")
    typer.echo(f"  feedback events: {lifecycle['feedback_count']}")
    typer.echo(f"  orphan nodes:    {lifecycle['orphan_count']}")
    typer.echo(f"  adr drafts:      {len(lifecycle['adr_drafts'])}")


def main() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    main()
