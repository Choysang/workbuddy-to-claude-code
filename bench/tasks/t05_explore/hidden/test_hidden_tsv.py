import datetime as dt
import io
import json

import pytest

from dataexport import get_exporter, list_formats
from dataexport.__main__ import main


def test_tsv_listed():
    assert "tsv" in list_formats()


def test_tsv_values_match_other_formats():
    records = [{"id": 1, "name": "x", "when": dt.datetime(2024, 1, 2, 3, 4, 5), "ok": False, "n": 2.0},
               {"id": 2}]
    text = get_exporter("tsv")(["id", "name", "when", "ok", "n"]).export(records)
    assert text == "id\tname\twhen\tok\tn\n1\tx\t2024-01-02T03:04:05\tfalse\t2\n2\t\t\t\t\n"


def test_tsv_escapes_control_characters():
    records = [{"a": "tab\there", "b": "line\nbreak\r", "c": "back\\slash"}]
    text = get_exporter("tsv")(["a", "b", "c"]).export(records)
    assert text == "a\tb\tc\ntab\\there\tline\\nbreak\\r\tback\\\\slash\n"
    assert all(line.count("\t") == 2 for line in text.splitlines())


def test_tsv_no_quoting():
    text = get_exporter("tsv")(["a"]).export([{"a": 'say "hi", ok'}])
    assert text == 'a\nsay "hi", ok\n'


def test_cli(tmp_path):
    src = tmp_path / "in.json"
    src.write_text(json.dumps([{"id": 1, "name": "a b"}]), encoding="utf-8")
    out = io.StringIO()
    assert main(["--format", "tsv", "--columns", "id,name", str(src)], out=out) == 0
    assert out.getvalue() == "id\tname\n1\ta b\n"


def test_exporter_uses_registry_contract():
    cls = get_exporter("tsv")
    assert cls.format_name == "tsv"
    with pytest.raises(ValueError):
        from dataexport.registry import register
        register("tsv")(type("Dup", (), {}))
