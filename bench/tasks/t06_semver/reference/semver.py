"""Version comparison for the release tooling (SemVer 2.0.0)."""
import functools
import re

_NUM = r"0|[1-9]\d*"
_PRE_ID = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER = re.compile(
    rf"^({_NUM})\.({_NUM})\.({_NUM})"
    rf"(?:-({_PRE_ID}(?:\.{_PRE_ID})*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def parse(version):
    match = _SEMVER.match(version) if isinstance(version, str) else None
    if not match:
        raise ValueError(f"invalid semver: {version!r}")
    major, minor, patch, pre, _build = match.groups()
    return int(major), int(minor), int(patch), tuple(pre.split(".")) if pre else ()


def _cmp(a, b):
    return (a > b) - (a < b)


def _cmp_identifier(a, b):
    a_num, b_num = a.isdigit(), b.isdigit()
    if a_num and b_num:
        return _cmp(int(a), int(b))
    if a_num != b_num:
        return -1 if a_num else 1
    return _cmp(a, b)


def compare(a, b):
    pa, pb = parse(a), parse(b)
    core = _cmp(pa[:3], pb[:3])
    if core:
        return core
    pre_a, pre_b = pa[3], pb[3]
    if not pre_a or not pre_b:
        return _cmp(not pre_a, not pre_b)
    for x, y in zip(pre_a, pre_b):
        result = _cmp_identifier(x, y)
        if result:
            return result
    return _cmp(len(pre_a), len(pre_b))


def sort_versions(versions):
    return sorted(versions, key=functools.cmp_to_key(compare))
