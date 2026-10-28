import json
from pathlib import Path

from .models import Task


def load(path):
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Task.from_dict(item) for item in data["tasks"]]


def save(path, tasks):
    payload = {"tasks": [t.to_dict() for t in tasks]}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def next_id(tasks):
    return max((t.id for t in tasks), default=0) + 1
