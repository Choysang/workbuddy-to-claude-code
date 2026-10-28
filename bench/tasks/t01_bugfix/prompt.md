The billing team reports three problems with the `invoicing` package in this workspace:

1. An invoice with three items at 0.10 each shows a subtotal of `0.30000000000000004` instead of `0.30`.
2. A 10% discount on a single 19.99 item gives 17.99 on some machines and 17.98 on others. Money must round half-up to whole cents (19.99 - 1.999 = 17.991 -> 17.99; 0.125 -> 0.13).
3. A discount above 100% produces a negative total. A discount outside 0..100 must raise `ValueError` as soon as it is set or used.

Fix the package. `subtotal()` and `total()` must return values that compare equal to `decimal.Decimal` amounts with two decimal places (for example `Decimal("0.30")`). Keep the public API (`Invoice`, `LineItem`, `add`, `subtotal`, `total`, `render`). Run the existing tests when you are done.
