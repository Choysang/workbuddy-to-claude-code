import math

from . import metrics
from .vector import Vector


class Shape:
    def area(self):
        raise NotImplementedError

    def contains(self, point):
        raise NotImplementedError


class Circle(Shape):
    def __init__(self, radius, center=Vector(0, 0)):
        self.radius = radius
        self.center = center

    def area(self):
        return math.pi * self.radius ** 2

    def contains(self, point):
        return metrics.euclidean_distance(self.center, point) <= self.radius


class Polygon(Shape):
    def __init__(self, points):
        self.points = list(points)

    def area(self):
        total = 0.0
        pts = self.points
        for i, p in enumerate(pts):
            q = pts[(i + 1) % len(pts)]
            total += p.x * q.y - q.x * p.y
        return abs(total) / 2

    def perimeter(self):
        pts = self.points
        return sum(metrics.euclidean_distance(p, pts[(i + 1) % len(pts)]) for i, p in enumerate(pts))
