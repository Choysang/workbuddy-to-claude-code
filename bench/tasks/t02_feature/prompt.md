Add task priorities to the `todo` app in this workspace.

Requirements:
- Every task has a priority: `low`, `normal` or `high`. Default is `normal`.
- `todo add "title" --priority high` sets it. An unknown priority makes `cli.main` return exit code 2 without changing the store (argparse's normal error exit is fine if `main` returns or raises `SystemExit(2)`).
- `todo list` shows the priority after the title in parentheses only when it is not `normal`, for example `[ ] 3: ship release (high)`.
- `todo list --sort priority` lists high first, then normal, then low; ties keep id order. Without `--sort`, order stays by id.
- The priority is saved in the JSON store. Store files written by the old version (no `priority` key) must still load, as `normal`.

The change touches the model, the storage and the CLI. Keep the existing tests passing and add tests for the new behavior.
