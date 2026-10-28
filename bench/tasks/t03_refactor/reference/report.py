"""Sales report generator."""

HEADER = "REGION          COUNT      TOTAL    REFUNDS"


def parse_rows(csv_text):
    header = None
    rows = []
    skipped = 0
    for line in csv_text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if header is None:
            header = [h.strip().lower() for h in line.split(",")]
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != len(header):
            skipped += 1
            continue
        row = dict(zip(header, parts))
        try:
            amount = float(row["amount"])
        except ValueError:
            skipped += 1
            continue
        rows.append((row["region"].title(), amount))
    return rows, skipped


def summarize(rows):
    summary = {}
    for region, amount in rows:
        count, total, refunds = summary.get(region, (0, 0.0, 0.0))
        if amount < 0:
            refunds = refunds + (-amount)
        else:
            count, total = count + 1, total + amount
        summary[region] = (count, total, refunds)
    return summary


def render(summary, skipped=0):
    out = [HEADER]
    grand_count, grand_total, grand_refunds = 0, 0.0, 0.0
    for region in sorted(summary, key=lambda r: (-summary[r][1], r)):
        c, t, r = summary[region]
        grand_count, grand_total, grand_refunds = grand_count + c, grand_total + t, grand_refunds + r
        out.append(f"{region:<12}{c:>9}{t:>11.2f}{r:>11.2f}")
    out.append("-" * 43)
    out.append(f"{'ALL':<12}{grand_count:>9}{grand_total:>11.2f}{grand_refunds:>11.2f}")
    if skipped:
        out.append(f"skipped {skipped} bad rows")
    return "\n".join(out)


def generate_report(csv_text):
    rows, skipped = parse_rows(csv_text)
    return render(summarize(rows), skipped)
