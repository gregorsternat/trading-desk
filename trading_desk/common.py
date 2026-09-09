import contextlib
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO-8601 string with timezone")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp needs an explicit timezone")
    return result


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text)
    os.replace(temporary, path)


@contextlib.contextmanager
def locked(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".write.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def profile():
    return read_json(ROOT / "config/profile.json")
