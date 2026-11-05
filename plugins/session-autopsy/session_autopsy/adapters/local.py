"""Private local state, explicitly separate from repository artifacts."""
from pathlib import Path
import os
import re
import tempfile


def cache_directory():
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "session-autopsy"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def private_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".autopsy-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


class PrivateEvidenceStore:
    def save(self, content):
        descriptor, name = tempfile.mkstemp(prefix="evidence-", suffix=".json", dir=cache_directory())
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        return Path(name)


def export_report(filename, content):
    """CLI output names cannot escape the workspace's private reports folder."""
    name = str(filename)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
        raise ValueError("Output must be a simple filename inside ./reports")
    if Path(name).suffix not in (".json", ".md", ".txt"):
        raise ValueError("Output must use .json, .md, or .txt; source logs are read-only")
    root = Path.cwd() / "reports"
    if root.is_symlink():
        raise ValueError("Reports directory must not be a symlink")
    root.mkdir(mode=0o700, exist_ok=True)
    return private_write(root / name, content)
