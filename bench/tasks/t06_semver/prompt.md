Our release tool crashes or mis-orders versions like `1.0.0-rc.1` and `1.0.0+build.5`. Make `semver.py` in this workspace follow Semantic Versioning 2.0.0 precedence rules exactly (section 11 of semver.org), including pre-release identifiers and build metadata.

- `compare(a, b)` returns -1, 0 or 1.
- `sort_versions(list)` sorts ascending by precedence; versions with equal precedence keep their input order.
- `parse(version)` and `compare` raise `ValueError` for strings that are not valid SemVer 2.0.0 (for example leading zeros in numeric identifiers, missing parts, empty identifiers).

Keep the existing tests passing and add your own.
