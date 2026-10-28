`python -m pytest` in this workspace fails before any test runs. Find out why and make the whole test suite pass.

Rules:
- Do not change anything under `tests/`.
- Keep the public API of `geomkit` (`Vector`, `Circle`, `Polygon`, `flatten`) and keep `Vector.inside(shape)` working.
- Fix root causes; do not delete features or skip tests.
