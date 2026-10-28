"""Version comparison for the release tooling."""


def parse(version):
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def compare(a, b):
    """Return -1, 0 or 1 like a classic cmp()."""
    pa, pb = parse(a), parse(b)
    return (pa > pb) - (pa < pb)


def sort_versions(versions):
    import functools
    return sorted(versions, key=functools.cmp_to_key(compare))
