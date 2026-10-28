import argparse
import json
import sys

from . import get_exporter, list_formats


def main(argv=None, out=None):
    out = out or sys.stdout
    parser = argparse.ArgumentParser(prog="dataexport")
    parser.add_argument("--format", required=True, choices=list_formats())
    parser.add_argument("--columns", required=True, help="comma-separated column names")
    parser.add_argument("input", help="JSON file with a list of records")
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as fh:
        records = json.load(fh)
    exporter = get_exporter(args.format)(args.columns.split(","))
    out.write(exporter.export(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
