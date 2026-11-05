"""Private local state, explicitly separate from repository artifacts."""
from pathlib import Path
import os
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
