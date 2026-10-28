from semver import compare, sort_versions


def test_basic():
    assert compare("1.2.3", "1.2.4") == -1
    assert compare("2.0.0", "1.9.9") == 1
    assert compare("1.0.0", "1.0.0") == 0


def test_sort():
    assert sort_versions(["1.10.0", "1.2.0", "1.9.0"]) == ["1.2.0", "1.9.0", "1.10.0"]
