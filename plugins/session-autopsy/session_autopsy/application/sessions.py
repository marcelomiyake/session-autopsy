"""Session discovery, unambiguous selection, and descendant collection."""
from pathlib import Path

from session_autopsy.domain.accounting import build_report


class SessionService:
    def __init__(self, sources):
        self.sources = sources

    def discover(self):
        sessions = []
        warnings = []
        for source, root in self.sources:
            for path in source.discover(root):
                try:
                    sessions.append(source.read(path))
                except (OSError, ValueError) as exc:
                    warnings.append(f"{path}: {exc}")
        return sorted(sessions, key=lambda s: s.updated, reverse=True), warnings

    def select(self, sessions, selector):
        if not selector:
            raise ValueError("Select a session ID, unique prefix, path, or explicit latest")
        if selector == "latest":
            candidates = [s for s in sessions if not s.parent_id]
            if not candidates:
                raise ValueError("No root sessions found")
            return candidates[0]
        exact = [s for s in sessions if s.agent_id == selector or s.path == str(Path(selector).expanduser().absolute())]
        matches = exact or [s for s in sessions if s.agent_id.startswith(selector)]
        if len(matches) != 1:
            raise ValueError(f"Session selector matched {len(matches)} sessions; use a full path or unique ID")
        return matches[0]

    def report(self, sessions, selected, catalog):
        family = [selected]
        known = {selected.agent_id}
        for _ in range(len(sessions)):
            children = [s for s in sessions if s.parent_id in known and s.agent_id not in known]
            if not children:
                break
            family.extend(children)
            known.update(s.agent_id for s in children)
        return build_report(family, catalog), family


def filtered_sessions(sessions, harness=None, since=None, until=None, cwd=None, query=None):
    roots = [s for s in sessions if not s.parent_id]
    if harness:
        roots = [s for s in roots if s.harness == harness]
    if since:
        roots = [s for s in roots if s.started >= since]
    if until:
        roots = [s for s in roots if s.started[:10] <= until]
    if cwd:
        roots = [s for s in roots if cwd.lower() in s.cwd.lower()]
    if query:
        roots = [s for s in roots if query.lower() in (s.prompt + s.title + s.cwd).lower()]
    return roots
