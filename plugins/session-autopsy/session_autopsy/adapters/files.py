"""Read a fixed byte snapshot; tolerate interrupted appends without modifying logs."""
import json
from pathlib import Path


def snapshot_rows(path: Path, warnings: list[str], size=None):
    size = path.stat().st_size if size is None else size
    with path.open("rb") as stream:
        remaining = size
        number = 0
        while remaining:
            line = stream.readline(remaining)
            remaining -= len(line)
            number += 1
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    yield number, row
            except ValueError:
                warnings.append(f"{path}:{number}: malformed or incomplete record")


def text_content(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict):
            text = block.get("text", block.get("content", ""))
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def user_prompt(text):
    return bool(text.strip()) and not text.lstrip().startswith((
        "<environment_context>", "<user_instructions>", "# AGENTS.md instructions",
        "<local-command", "<command-", "<system-reminder>"))


def remember_excerpt(session, text, kind, line):
    if text:
        session.excerpts.append({"kind": kind, "characters": len(text),
                                 "text": text[:1200], "line": line, "path": session.path})
        session.excerpts.sort(key=lambda item: item["characters"], reverse=True)
        del session.excerpts[12:]


def remember_time(session, timestamp):
    if timestamp:
        session.started = session.started or timestamp
        session.updated = timestamp
