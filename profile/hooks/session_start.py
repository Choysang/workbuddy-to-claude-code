#!/usr/bin/env python3
"""SessionStart: hand the model a compact picture of the repository it just entered.

Orientation only — branch, dirty state, last commit, detected stack. The model
should not have to burn a tool call on `git status` before it knows where it is.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _hooklib as H  # noqa: E402

STACK_MARKERS = (
    ("package.json", "node"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("pom.xml", "java-maven"),
    ("build.gradle", "java-gradle"),
    ("CMakeLists.txt", "cmake"),
)


def detect_stack(root: Path) -> list[str]:
    found = [label for name, label in STACK_MARKERS if (root / name).exists()]
    if (root / "tests").is_dir() or (root / "test").is_dir():
        found.append("has-tests")
    if (root / "Dockerfile").exists():
        found.append("docker")
    return sorted(set(found))


def repo_state(root: Path) -> list[str]:
    branch = H.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    if not branch:
        return []
    lines = [f"branch: {branch}"]
    head = H.run(["git", "log", "-1", "--pretty=%h %s"], root)
    if head:
        lines.append(f"head: {head[:120]}")
    status = H.run(["git", "status", "--porcelain"], root)
    dirty = [line for line in status.splitlines() if line.strip()]
    lines.append(f"uncommitted: {len(dirty)} file(s)")
    if dirty:
        preview = ", ".join(line[3:].strip() for line in dirty[:5])
        lines.append(f"touched: {preview}")
    ahead = H.run(["git", "rev-list", "--count", "@{u}..HEAD"], root)
    if ahead and ahead != "0":
        lines.append(f"ahead-of-upstream: {ahead} commit(s)")
    return lines


def main() -> None:
    data = H.payload()
    root = H.cwd(data)
    repository = repo_state(root)
    if not repository:
        return
    parts = [f"<repo_state>", f"cwd: {root.as_posix()}"]
    parts.extend(repository)
    stack = detect_stack(root)
    if stack:
        parts.append("stack: " + ", ".join(stack))
    handoff = root / ".harness" / "HANDOFF.md"
    if handoff.is_file():
        parts.append("handoff: .harness/HANDOFF.md 存在，动手前先读它核对磁盘状态")
    parts.append("</repo_state>")
    H.emit("\n".join(parts), event="SessionStart")
    H.log("session_start", f"{root} {len(parts)} lines")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:  # a hook crash must never block the session
        H.log("session_start", f"error {type(error).__name__}: {error}")
        raise SystemExit(0)
