Refactor `report.py` in this workspace without changing its output.

Split `generate_report(csv_text)` into three public functions in the same module:
- `parse_rows(csv_text)` returns `(rows, skipped)`: `rows` is a list of `(region, amount)` tuples, region title-cased and amount a float, in input order; `skipped` counts malformed rows (wrong column count or non-numeric amount). Blank lines and lines starting with `#` are ignored and not counted.
- `summarize(rows)` returns a dict mapping region to a `(count, total, refunds)` tuple. Negative amounts add their absolute value to `refunds` and do not count; non-negative amounts add 1 to `count` and add to `total`.
- `render(summary, skipped=0)` returns the report text exactly as today.

`generate_report` must keep its signature and output and become a thin composition of the three (a few lines). Behavior for every input must stay byte-identical, including ordering and the skipped-rows line. Before refactoring, add characterization tests that pin the current behavior for edge cases; keep them in `tests/`.
