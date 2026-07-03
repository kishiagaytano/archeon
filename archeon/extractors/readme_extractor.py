"""Extract README sections and inline code comments from a repository."""

from __future__ import annotations

import re
from pathlib import Path

import typer

from archeon.ingest import IGNORED_DIRS
from archeon.schema import SourceRecord, SourceType

from .jsonl_io import write_jsonl

app = typer.Typer(
    name="readme_extractor",
    help="Extract README sections and code comments into SourceRecord JSONL.",
    no_args_is_help=True,
)

README_NAMES = {"readme.md", "readme.rst", "readme.txt"}
COMMENT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb"}
PY_SINGLE_LINE = re.compile(r"^\s*#(?!!)\s*(.+)$")
PY_BLOCK = re.compile(r'"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\'', re.MULTILINE)
JS_SINGLE_LINE = re.compile(r"^\s*//\s*(.+)$")
JS_BLOCK = re.compile(r"/\*([\s\S]*?)\*/", re.MULTILINE)
HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


def _iter_repo_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def _extract_readme_sections(path: Path, repo: Path) -> list[SourceRecord]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_path = str(path.relative_to(repo))
    lines = text.splitlines()
    records: list[SourceRecord] = []

    if not lines:
        return records

    sections: list[tuple[str, list[str]]] = []
    current_title = "Introduction"
    current_lines: list[str] = []

    for line in lines:
        match = HEADING.match(line)
        if match:
            if current_lines or current_title != "Introduction":
                sections.append((current_title, current_lines))
            current_title = match.group(2).strip()
            current_lines = []
            continue
        current_lines.append(line)

    sections.append((current_title, current_lines))

    for title, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body and title == "Introduction" and len(sections) == 1:
            body = text.strip()
        if not body:
            continue

        locator = f"{rel_path}#{_slug(title)}"
        records.append(
            SourceRecord(
                source=SourceType.README,
                content=f"## {title}\n\n{body}".strip(),
                metadata={
                    "path": rel_path,
                    "section": title,
                    "locator": locator,
                },
            )
        )

    return records


def _meaningful_comment(text: str) -> bool:
    cleaned = " ".join(text.split())
    if len(cleaned) < 12:
        return False
    lowered = cleaned.lower()
    if lowered in {"todo", "fixme", "note", "type: ignore"}:
        return False
    return True


def _extract_python_comments(path: Path, repo: Path) -> list[SourceRecord]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_path = str(path.relative_to(repo))
    records: list[SourceRecord] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        match = PY_SINGLE_LINE.match(line)
        if match and _meaningful_comment(match.group(1)):
            records.append(
                SourceRecord(
                    source=SourceType.DOC,
                    content=match.group(1).strip(),
                    metadata={"path": rel_path, "line": line_no, "locator": f"{rel_path}:{line_no}"},
                )
            )

    for match in PY_BLOCK.finditer(text):
        block = (match.group(1) or match.group(2) or "").strip()
        if not _meaningful_comment(block):
            continue
        line_no = text[: match.start()].count("\n") + 1
        records.append(
            SourceRecord(
                source=SourceType.DOC,
                content=block,
                metadata={"path": rel_path, "line": line_no, "locator": f"{rel_path}:{line_no}"},
            )
        )

    return records


def _extract_c_style_comments(path: Path, repo: Path) -> list[SourceRecord]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_path = str(path.relative_to(repo))
    records: list[SourceRecord] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        match = JS_SINGLE_LINE.match(line)
        if match and _meaningful_comment(match.group(1)):
            records.append(
                SourceRecord(
                    source=SourceType.DOC,
                    content=match.group(1).strip(),
                    metadata={"path": rel_path, "line": line_no, "locator": f"{rel_path}:{line_no}"},
                )
            )

    for match in JS_BLOCK.finditer(text):
        block = " ".join(match.group(1).split())
        if not _meaningful_comment(block):
            continue
        line_no = text[: match.start()].count("\n") + 1
        records.append(
            SourceRecord(
                source=SourceType.DOC,
                content=block,
                metadata={"path": rel_path, "line": line_no, "locator": f"{rel_path}:{line_no}"},
            )
        )

    return records


def extract_readme_and_comments(repo: Path) -> list[SourceRecord]:
    """Extract README sections and inline comments from ``repo``."""
    repo = repo.resolve()
    records: list[SourceRecord] = []

    for path in _iter_repo_files(repo):
        if path.name.lower() in README_NAMES:
            records.extend(_extract_readme_sections(path, repo))
            continue

        suffix = path.suffix.lower()
        if suffix == ".py":
            records.extend(_extract_python_comments(path, repo))
        elif suffix in COMMENT_EXTENSIONS - {".py"}:
            records.extend(_extract_c_style_comments(path, repo))

    return records


@app.command()
def main(
    repo: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to the repository to scan.",
    ),
    output: Path = typer.Option(
        Path(".archeon/readme.jsonl"),
        "--out",
        "-o",
        help="Output JSONL path.",
    ),
) -> None:
    """Extract README and comment records and write ``.jsonl`` output."""
    records = extract_readme_and_comments(repo)
    count = write_jsonl(output, records)
    typer.echo(f"Wrote {count} readme/doc record(s) to {output}")


if __name__ == "__main__":
    app()
