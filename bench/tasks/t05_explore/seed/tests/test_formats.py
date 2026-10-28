import datetime as dt

from dataexport import get_exporter, list_formats

RECORDS = [{"id": 1, "name": "a b", "when": dt.date(2024, 1, 2), "ok": True}, {"id": 2, "name": None}]


def test_formats_registered():
    assert {"csv", "jsonl", "logfmt"} <= set(list_formats())


def test_csv():
    text = get_exporter("csv")(["id", "name", "when", "ok"]).export(RECORDS)
    assert text == "id,name,when,ok\n1,a b,2024-01-02,true\n2,,,\n"


def test_logfmt():
    text = get_exporter("logfmt")(["id", "name"]).export(RECORDS)
    assert text == 'id=1 name="a b"\nid=2 name=\n'
