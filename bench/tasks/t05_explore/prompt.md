Users of the `dataexport` package in this workspace want a tab-separated export.

Add a `tsv` format so that `python -m dataexport --format tsv --columns id,name input.json` works and `list_formats()` includes `tsv`. The first line is the tab-separated column names. Each record is one line. Values are written exactly as the other formats render them, and a value must never break the line/column structure: use the same escaping the project already uses for its other line-based format. No quoting.

Explore the package first and follow its existing conventions. Add tests.
