import math

from geomkit import Circle, Polygon, Vector, flatten


def test_vector_ops():
    assert Vector(1, 2) + Vector(3, 4) == Vector(4, 6)
    assert Vector(3, 4).length() == 5


def test_circle():
    c = Circle(2)
    assert math.isclose(c.area(), 4 * math.pi)
    assert c.contains(Vector(1, 1))
    assert not c.contains(Vector(2, 2))


def test_polygon():
    square = Polygon([Vector(0, 0), Vector(2, 0), Vector(2, 2), Vector(0, 2)])
    assert square.area() == 4
    assert square.perimeter() == 8


def test_flatten():
    assert list(flatten([1, [2, (3, "ab")], [[4]]])) == [1, 2, 3, "ab", 4]
