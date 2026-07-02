"""Extract structured commit history from a local git repository."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from archeon.schema import SourceRecord, SourceType

from .jsonl_io import write_jsonl

_FIELD_SEP = "\x1f"
_COMMIT_END = "\x1e"

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".sqlite",
    ".db",
    ".pyc",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
}

app = typer.Typer(
    name="git_extractor",
    help="Extract git commit history into SourceRecord JSONL.",
    no_args_is_help=True,
)


class GitExtractorError(RuntimeError):
    """Raised when git commands fail or the path is not a repository."""


def _run_git(repo: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitExtractorError("git is not installed or not on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise GitExtractorError(stderr or f"git {' '.join(args)} failed") from exc
    return completed.stdout


def _is_git_repo(repo: Path) -> bool:
    try:
        _run_git(repo, "rev-parse", "--git-dir")
    except GitExtractorError:
        return False
    return True


def _changed_files(repo: Path, sha: str) -> list[str]:
    output = _run_git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    files = [line.strip() for line in output.splitlines() if line.strip()]
    if files:
        return _filter_text_files(files)
    output = _run_git(repo, "show", "--name-only", "--format=", sha)
    return _filter_text_files([line.strip() for line in output.splitlines() if line.strip()])


def _diff_summary(repo: Path, sha: str) -> str:
    output = _run_git(repo, "show", "--stat", "--format=", sha)
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1] if lines[-1].endswith(")") else "\n".join(lines)


def _is_merge_commit(repo: Path, sha: str) -> bool:
    output = _run_git(repo, "rev-list", "--parents", "-n", "1", sha)
    parents = output.strip().split()
    return len(parents) > 2


def _filter_text_files(files: list[str]) -> list[str]:
    return [
        path
        for path in files
        if Path(path).suffix.lower() not in BINARY_EXTENSIONS
    ]


def _should_skip_commit(subject: str, body: str, files: list[str]) -> bool:
    if subject.strip() or body.strip():
        return False
    return not files


def _build_content(subject: str, body: str, files: list[str], diff_summary: str) -> str:
    parts: list[str] = []
    subject = subject.strip()
    body = body.strip()

    if subject:
        parts.append(subject)
    if body and body != subject:
        parts.append(body)
    if files:
        parts.append("Files changed: " + ", ".join(files))
    if diff_summary:
        parts.append("Diff summary: " + diff_summary)
    return "\n\n".join(parts)


def extract_commits(
    repo: Path,
    *,
    max_commits: int | None = None,
    since_sha: str | None = None,
) -> list[SourceRecord]:
    """Parse ``git log`` into :class:`SourceRecord` rows."""
    repo = repo.resolve()
    if not _is_git_repo(repo):
        raise GitExtractorError(f"{repo} is not a git repository.")

    format_spec = (
        f"%H{_FIELD_SEP}%an{_FIELD_SEP}%ae{_FIELD_SEP}%aI{_FIELD_SEP}%s{_FIELD_SEP}%b{_COMMIT_END}"
    )
    args = ["log", f"--pretty=format:{format_spec}", "--reverse"]
    if since_sha:
        args.insert(1, f"{since_sha}..HEAD")
    if max_commits is not None:
        args.insert(1, f"-n{max_commits}")

    raw = _run_git(repo, *args)
    records: list[SourceRecord] = []

    for chunk in raw.split(_COMMIT_END):
        chunk = chunk.strip()
        if not chunk:
            continue

        fields = chunk.split(_FIELD_SEP, 5)
        if len(fields) < 5:
            continue

        sha, author, email, date, subject = fields[:5]
        body = fields[5] if len(fields) > 5 else ""
        files = _changed_files(repo, sha)
        if _should_skip_commit(subject, body, files):
            continue

        diff_summary = _diff_summary(repo, sha)
        content = _build_content(subject, body, files, diff_summary)
        if not content.strip():
            continue

        metadata: dict = {
            "sha": sha,
            "author": author,
            "email": email,
            "date": date[:10] if len(date) >= 10 else date,
            "files": files,
            "diff_summary": diff_summary,
            "locator": sha[:7],
        }
        if _is_merge_commit(repo, sha):
            metadata["is_merge"] = True

        records.append(
            SourceRecord(
                source=SourceType.COMMIT,
                content=content,
                metadata=metadata,
            )
        )

    return records


@app.command()
def main(
    repo: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Path to a local git repository.",
    ),
    output: Path = typer.Option(
        Path(".archeon/commits.jsonl"),
        "--out",
        "-o",
        help="Output JSONL path.",
    ),
    max_commits: int | None = typer.Option(
        None,
        "--max-commits",
        help="Limit the number of commits extracted (newest first).",
    ),
    since_sha: str | None = typer.Option(
        None,
        "--since-sha",
        help="Only include commits after this SHA.",
    ),
) -> None:
    """Extract commits from a repository and write ``.jsonl`` output."""
    records = extract_commits(repo, max_commits=max_commits, since_sha=since_sha)
    count = write_jsonl(output, records)
    typer.echo(f"Wrote {count} commit record(s) to {output}")


if __name__ == "__main__":
    app()
