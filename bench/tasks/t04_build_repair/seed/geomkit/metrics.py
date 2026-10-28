import math


def euclidean_distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)
