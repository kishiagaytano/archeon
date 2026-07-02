"""Command-line interface for Archeon."""

from pathlib import Path

import typer

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
) -> None:
    """Placeholder for repository ingestion."""
    typer.echo(f"Placeholder: would ingest repository at {repo}.")
    typer.echo("Cognee integration is not implemented yet.")


@app.command()
def why(
    file: Path = typer.Argument(
        ...,
        help="Path to the file to explain.",
        exists=False,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Placeholder for decision explanation."""
    typer.echo(f"Placeholder: would explain why {file} exists or changed.")
    typer.echo("Cognee integration is not implemented yet.")


@app.command()
def status() -> None:
    """Show Archeon status."""
    typer.echo("Archeon CLI skeleton is ready.")
    typer.echo("Cognee integration is not implemented yet.")


def main() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    main()
