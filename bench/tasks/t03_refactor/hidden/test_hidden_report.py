import ast
import inspect
import textwrap

import report

ORIGINAL = textwrap.dedent('''
def generate_report(csv_text):
    lines = csv_text.splitlines()
    header = None
    data = {}
    order = []
    skipped = 0
    for line in lines:
        if not line.strip():
            continue
        if line.strip().startswith("#"):
            continue
        if header is None:
            header = [h.strip().lower() for h in line.split(",")]
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != len(header):
            skipped += 1
            continue
        row = dict(zip(header, parts))
        region = row["region"].title()
        try:
            amount = float(row["amount"])
        except ValueError:
            skipped += 1
            continue
        if region not in data:
            data[region] = [0, 0.0, 0.0]
            order.append(region)
        if amount < 0:
            data[region][2] = data[region][2] + (-amount)
        else:
            data[region][0] = data[region][0] + 1
            data[region][1] = data[region][1] + amount
    out = []
    out.append("REGION          COUNT      TOTAL    REFUNDS")
    grand_count = 0
    grand_total = 0.0
    grand_refunds = 0.0
    for region in sorted(order, key=lambda r: (-data[r][1], r)):
        c = data[region][0]
        t = data[region][1]
        r = data[region][2]
        grand_count = grand_count + c
        grand_total = grand_total + t
        grand_refunds = grand_refunds + r
        out.append(f"{region:<12}{c:>9}{t:>11.2f}{r:>11.2f}")
    out.append("-" * 43)
    out.append(f"{'ALL':<12}{grand_count:>9}{grand_total:>11.2f}{grand_refunds:>11.2f}")
    if skipped:
        out.append(f"skipped {skipped} bad rows")
    return "\\n".join(out)
''')
_ns = {}
exec(ORIGINAL, _ns)
original = _ns["generate_report"]

CASES = [
    "region,amount\nnorth,10\nsouth,5.5\nnorth,2.25\n",
    "Region , Amount\n\n# comment\nwest,1\nWEST,2\neast,abc\neast,3,extra\neast,-4\n",
    "amount,region\n7,south\n-1.5,south\n7,north\n",
    "region,amount\n",
    "region,amount\nnew york,1\nnew york,-1\n",
    "region,amount\nb,5\na,5\nc,-2\n",
    "  # only comment\nregion,amount\n x , 1e3 \n",
]


def test_output_identical_to_original():
    for case in CASES:
        assert report.generate_report(case) == original(case), case


def test_parse_rows():
    rows, skipped = report.parse_rows(CASES[1])
    assert rows == [("West", 1.0), ("West", 2.0), ("East", -4.0)]
    assert skipped == 2


def test_parse_rows_column_order_from_header():
    rows, skipped = report.parse_rows(CASES[2])
    assert rows == [("South", 7.0), ("South", -1.5), ("North", 7.0)]
    assert skipped == 0


def test_summarize():
    summary = report.summarize([("West", 1.0), ("West", 2.0), ("East", -4.0)])
    assert summary == {"West": (2, 3.0, 0.0), "East": (0, 0.0, 4.0)}


def test_render_matches_generate():
    rows, skipped = report.parse_rows(CASES[1])
    assert report.render(report.summarize(rows), skipped) == original(CASES[1])


def test_generate_report_is_thin():
    tree = ast.parse(textwrap.dedent(inspect.getsource(report.generate_report)))
    body = tree.body[0].body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    assert len(body) <= 4
    loops = [n for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While))]
    assert not loops
