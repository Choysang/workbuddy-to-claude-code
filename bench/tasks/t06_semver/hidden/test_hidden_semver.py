import pytest

from semver import compare, parse, sort_versions

ORDERED = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
           "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1", "1.1.0", "2.0.0"]


def test_spec_precedence_chain():
    for lo, hi in zip(ORDERED, ORDERED[1:]):
        assert compare(lo, hi) == -1, (lo, hi)
        assert compare(hi, lo) == 1, (hi, lo)


def test_sort_full_list():
    shuffled = ORDERED[::-1][3:] + ORDERED[::-1][:3]
    assert sort_versions(shuffled) == ORDERED


def test_build_metadata_ignored():
    assert compare("1.0.0+build.1", "1.0.0+build.2") == 0
    assert compare("1.0.0-alpha+001", "1.0.0-alpha") == 0
    assert sort_versions(["1.0.0+b", "1.0.0+a"]) == ["1.0.0+b", "1.0.0+a"]


def test_numeric_identifiers_lower_than_alnum():
    assert compare("1.0.0-1", "1.0.0-a") == -1
    assert compare("1.0.0-alpha.10", "1.0.0-alpha.9") == 1
    assert compare("1.0.0-x-y", "1.0.0-x") == 1


def test_large_numbers():
    assert compare("1.0.0", "1.0.18446744073709551616") == -1


@pytest.mark.parametrize("bad", ["1.0", "01.0.0", "1.0.0-", "1.0.0-01", "1.0.0+", "1.0.0-a..b", "v1.0.0", "1.0.0-a_b", ""])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse(bad)
    with pytest.raises(ValueError):
        compare(bad, "1.0.0")


@pytest.mark.parametrize("good", ["0.0.0", "1.0.0-0", "1.0.0-0a", "1.0.0-a.0", "1.0.0+001", "1.0.0-x.7.z.92+exp.sha.5114f85"])
def test_valid(good):
    parse(good)
    assert compare(good, good) == 0
