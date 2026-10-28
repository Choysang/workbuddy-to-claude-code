import io
import json

import pytest

from todo import cli, storage
from todo.models import Task


def run(argv, path):
    out = io.StringIO()
    try:
        code = cli.main(argv, path, out=out)
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue()


def test_default_priority_is_normal(tmp_path):
    store = tmp_path / "t.json"
    run(["add", "a"], store)
    assert storage.load(store)[0].priority == "normal"


def test_priority_round_trips_in_json(tmp_path):
    store = tmp_path / "t.json"
    run(["add", "a", "--priority", "high"], store)
    data = json.loads(store.read_text(encoding="utf-8"))
    assert data["tasks"][0]["priority"] == "high"
    assert storage.load(store)[0].priority == "high"


def test_old_store_without_priority_loads(tmp_path):
    store = tmp_path / "t.json"
    store.write_text(json.dumps({"tasks": [{"id": 1, "title": "old", "done": False}]}), encoding="utf-8")
    tasks = storage.load(store)
    assert tasks[0].priority == "normal"
    code, text = run(["list"], store)
    assert code == 0 and "[ ] 1: old" in text and "(" not in text


def test_invalid_priority_exit_2_and_store_unchanged(tmp_path):
    store = tmp_path / "t.json"
    run(["add", "a"], store)
    before = store.read_text(encoding="utf-8")
    code, _ = run(["add", "b", "--priority", "urgent"], store)
    assert code == 2
    assert store.read_text(encoding="utf-8") == before


def test_list_shows_non_normal_priority(tmp_path):
    store = tmp_path / "t.json"
    run(["add", "ship release", "--priority", "high"], store)
    run(["add", "tidy", "--priority", "low"], store)
    run(["add", "plain"], store)
    _, text = run(["list"], store)
    lines = text.strip().splitlines()
    assert lines == ["[ ] 1: ship release (high)", "[ ] 2: tidy (low)", "[ ] 3: plain"]


def test_sort_by_priority_stable(tmp_path):
    store = tmp_path / "t.json"
    for title, prio in [("a", "low"), ("b", "high"), ("c", "normal"), ("d", "high"), ("e", "low")]:
        run(["add", title, "--priority", prio], store)
    _, text = run(["list", "--sort", "priority"], store)
    ids = [line.split(":")[0].split()[-1] for line in text.strip().splitlines()]
    assert ids == ["2", "4", "3", "1", "5"]


def test_done_keeps_priority(tmp_path):
    store = tmp_path / "t.json"
    run(["add", "a", "--priority", "high"], store)
    run(["done", "1"], store)
    task = storage.load(store)[0]
    assert task.done and task.priority == "high"


def test_model_dict_round_trip():
    task = Task(id=1, title="x", priority="low")
    assert Task.from_dict(task.to_dict()) == task
