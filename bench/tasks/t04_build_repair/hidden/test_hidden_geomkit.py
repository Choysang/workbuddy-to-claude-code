import hashlib
import math
from pathlib import Path

from geomkit import Circle, Polygon, Vector, flatten

# sha256 of tests/test_geomkit.py with LF line endings, as shipped in the seed.
VISIBLE_TEST_SHA256 = "0aaea2fabcf9f8e4cfc1d846b0ce4630b153c705525db505f11c366eda0a8b3c"


def test_visible_tests_unchanged():
    text = Path("tests/test_geomkit.py").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == VISIBLE_TEST_SHA256


def test_vector_inside_shape():
    assert Vector(0.5, 0.5).inside(Circle(1))
    assert not Vector(3, 0).inside(Circle(1, center=Vector(0, 0)))


def test_circle_with_center():
    c = Circle(1, center=Vector(5, 5))
    assert c.contains(Vector(5.5, 5.5))
    assert not c.contains(Vector(0, 0))


def test_triangle():
    tri = Polygon([Vector(0, 0), Vector(3, 0), Vector(0, 4)])
    assert tri.area() == 6
    assert math.isclose(tri.perimeter(), 12)


def test_flatten_generators_and_bytes():
    assert list(flatten([b"ab", (x for x in [1, [2]])])) == [b"ab", 1, 2]


def test_import_order_independent():
    import importlib
    import sys
    for name in [m for m in sys.modules if m == "geomkit" or m.startswith("geomkit.")]:
        del sys.modules[name]
    shapes = importlib.import_module("geomkit.shapes")
    vector = importlib.import_module("geomkit.vector")
    assert shapes.Circle(1).contains(vector.Vector(0, 0))
