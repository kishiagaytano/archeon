"""Load synthetic history fixtures from demo-style repositories."""

from __future__ import annotations

import json
import re
from pathlib import Path

from archeon.schema import SourceRecord, SourceType

HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


def load_demo_commits_jsonl(repo: Path) -> list[SourceRecord]:
    """Convert ``history/commits.jsonl`` demo rows into :class:`SourceRecord`s."""
    path = repo / "history" / "commits.jsonl"
    if not path.is_file():
        return []

    records: list[SourceRecord] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        message = (data.get("message") or "").strip()
        why = (data.get("why") or "").strip()
        files = data.get("files") or []

        parts: list[str] = []
        if message:
            parts.append(message)
        if why:
            parts.append(f"Why: {why}")
        if files:
            parts.append("Files changed: " + ", ".join(files))

        content = "\n\n".join(parts).strip()
        if not content:
            continue

        sha = data.get("sha", "")
        records.append(
            SourceRecord(
                source=SourceType.COMMIT,
                content=content,
                metadata={
                    "sha": sha,
                    "author": data.get("author"),
                    "date": data.get("date"),
                    "pr": data.get("pr"),
                    "issues": data.get("issues", []),
                    "files": files,
                    "locator": sha[:7] if sha else f"line-{line_no}",
                    "fixture": True,
                },
            )
        )
    return records


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def _markdown_sections(path: Path, repo: Path, source: SourceType) -> list[SourceRecord]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel_path = str(path.relative_to(repo))
    lines = text.splitlines()

    sections: list[tuple[str, list[str]]] = []
    current_title = path.stem.replace("-", " ").title()
    current_lines: list[str] = []

    for line in lines:
        match = HEADING.match(line)
        if match and match.group(1) == "##":
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = match.group(2).strip()
            current_lines = []
            continue
        if match and match.group(1) == "#" and not sections and not current_lines:
            current_title = match.group(2).strip()
            continue
        current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    records: list[SourceRecord] = []
    for title, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        records.append(
            SourceRecord(
                source=source,
                content=f"## {title}\n\n{body}".strip(),
                metadata={
                    "path": rel_path,
                    "section": title,
                    "locator": f"{rel_path}#{_slug(title)}",
                    "fixture": True,
                },
            )
        )
    return records


def load_history_markdown(repo: Path) -> list[SourceRecord]:
    """Load ``history/*.md`` and ``docs/*.md`` decision writeups."""
    records: list[SourceRecord] = []
    for folder, source in (
        ("history", SourceType.OTHER),
        ("docs", SourceType.ADR),
    ):
        root = repo / folder
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.md")):
            source_type = SourceType.ISSUE if path.name == "issues.md" else source
            if path.name == "pull-requests.md":
                source_type = SourceType.PULL_REQUEST
            records.extend(_markdown_sections(path, repo, source_type))
    return records
