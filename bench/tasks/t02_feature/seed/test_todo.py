import io

from todo import cli


def run(argv, path):
    out = io.StringIO()
    code = cli.main(argv, path, out=out)
    return code, out.getvalue()


def test_add_and_list(tmp_path):
    store = tmp_path / "todo.json"
    run(["add", "buy milk"], store)
    code, text = run(["list"], store)
    assert code == 0
    assert "[ ] 1: buy milk" in text
