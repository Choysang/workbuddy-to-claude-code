"""Minimal CSV line parsing for supplier price feeds (RFC 4180 subset)."""

from decimal import Decimal


def parse_line(line: str, sep: str = ",") -> list:
    """Split one CSV line. Fields may be wrapped in double quotes; inside quotes,
    `sep` is literal and a doubled quote ("") stands for one quote character.
    Unquoted fields are returned as-is (no trimming)."""
    fields, current, quoted, i = [], [], False, 0
    while i < len(line):
        ch = line[i]
        if quoted:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    current.append('""')
                    i += 1
                else:
                    quoted = False
            else:
                current.append(ch)
        elif ch == '"':
            quoted = True
        elif ch == sep:
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    fields.append("".join(current))
    return fields


def parse_price_feed(text: str) -> dict:
    """Parse `sku,price` lines (with a header line) into {sku: Decimal price}.
    Blank lines are skipped."""
    result = {}
    for raw in text.splitlines()[1:]:
        if not raw.strip():
            continue
        sku, price = parse_line(raw)[:2]
        result[sku] = Decimal(price)
    return result
