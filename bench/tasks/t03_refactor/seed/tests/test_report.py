import report

SAMPLE = """region,amount
north,10
south,5.5
north,2.25
"""


def test_golden_output():
    assert report.generate_report(SAMPLE) == "\n".join([
        "REGION          COUNT      TOTAL    REFUNDS",
        "North               2      12.25       0.00",
        "South               1       5.50       0.00",
        "-" * 43,
        "ALL                 3      17.75       0.00",
    ])
