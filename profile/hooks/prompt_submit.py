#!/usr/bin/env python3
"""UserPromptSubmit: keep the clock and the workspace honest, once per turn.

Two things go stale inside a long session: the date the model believes it is, and
whether the working tree still looks like it did. Both are cheap to restate and
expensive to get wrong.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _hooklib as H  # noqa: E402

PARALLEL_HINTS = ("并行", "同时", "一起改", "lanes", "parallel", "ultrawork", "多线程", "拆分")


def main() -> None:
    data = H.payload()
    root = H.cwd(data)
    lines = [f"now: {time.strftime('%Y-%m-%d %H:%M %A')}"]

    status = H.run(["git", "status", "--porcelain"], root, timeout=2.0)
    if status:
        dirty = [line for line in status.splitlines() if line.strip()]
        if dirty:
            lines.append(f"uncommitted: {len(dirty)} file(s)")

    prompt = data.get("prompt")
    if isinstance(prompt, str) and any(hint in prompt.lower() for hint in PARALLEL_HINTS):
        lines.append("提示：本次请求可能可拆分。先判断子任务是否真的互不依赖（无文件重叠、无先后依赖）；"
                     "成立就用 /lanes 并行派出，不成立就串行并说明原因。")

    H.emit("<turn_context>\n" + "\n".join(lines) + "\n</turn_context>", event="UserPromptSubmit")


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
    except Exception as error:
        H.log("prompt_submit", f"error {type(error).__name__}: {error}")
        raise SystemExit(0)
