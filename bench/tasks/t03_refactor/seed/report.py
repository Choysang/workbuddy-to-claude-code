"""Sales report generator. Works, but nobody wants to touch it."""


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
    return "\n".join(out)
