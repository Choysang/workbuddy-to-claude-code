"""Static and runtime verification for the installed harness."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import common as C
import install
import workspace as W

MARKER = C.PROMPT_MARKER
HOOK_SCRIPTS = ("session_start.py", "pre_tool_guard.py", "post_edit_check.py")

PASS, WARN, FAIL = "pass", "warn", "fail"
LABELS = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL"}

# The desktop app keeps settings.json in memory and periodically flushes it back
# to disk, which reverts keys it does not model (fileCheckpointingEnabled,
# alwaysThinkingEnabled, per-plugin enable flags). A check that fails only
# because of that flush is a warning, not a defect in the harness.
STALE_HINT = "运行中的 WorkBuddy 回写了 settings.json；关闭 WorkBuddy 后重跑 apply 与 verify"


def _state(value: bool | str) -> str:
    if isinstance(value, str):
        return value if value in LABELS else (PASS if value else FAIL)
    return PASS if value else FAIL


def _settings_rewritten(cfg: Path) -> bool:
    """True when settings.json was touched after the last apply recorded its stamp."""
    state = C.read_json(C.state_dir(cfg) / "state.json", default={}) or {}
    applied = state.get("applied")
    target = cfg / "settings.json"
    if not applied or not target.is_file():
        return False
    try:
        stamp = time.mktime(time.strptime(str(applied), "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return False
    return target.stat().st_mtime > stamp + 1


def _frontmatter(path: Path) -> dict:
    """Parse the leading `---` block.

    The closing fence is optional: a hand-written agent file that forgets it used
    to raise IndexError and take the whole report down.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r"^---[ \t]*\r?\n(.*?)(?:\r?\n---[ \t]*(?:\r?\n|\Z)|\Z)", text, re.S)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def _run_hook(script: Path, payload: dict, cfg: Path, *, stdout: bool = False) -> tuple[int, str]:
    env = {**os.environ, "WORKBUDDY_CONFIG_DIR": str(cfg)}
    try:
        result = subprocess.run(
            [C.interpreter(), str(script)],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return 124, "hook 超时（60s）"
    except OSError as error:
        return 125, f"无法启动解释器：{error}"
    return result.returncode, ((result.stdout if stdout else result.stderr) or b"").decode("utf-8", "replace")


def static_checks(cfg: Path) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []

    def add(name: str, state: bool | str, detail: str = "") -> None:
        checks.append((name, _state(state), detail))

    add("配置目录", cfg.is_dir(), str(cfg))
    if not cfg.is_dir():
        return checks

    rewritten = _settings_rewritten(cfg)

    def add_volatile(name: str, ok: bool, detail: str = "") -> None:
        """Fail only when the harness is really wrong, warn when the app reverted it."""
        if ok:
            add(name, PASS, detail)
        elif rewritten:
            add(name, WARN, f"{detail}；{STALE_HINT}" if detail else STALE_HINT)
        else:
            add(name, FAIL, detail)

    memory = cfg / "CODEBUDDY.md"
    text = memory.read_text(encoding="utf-8", errors="replace") if memory.is_file() else ""
    add("常驻记忆 CODEBUDDY.md", bool(text) and len(text) <= 6000,
        f"{len(text)} 字符" if text else "缺失")
    add("记忆内容完整", "## 委派" in text and "## 验证" in text, "")

    rules = cfg / "rules"
    leftovers = [p.name for p in rules.glob("*.md")] if rules.is_dir() else []
    add("无重复常驻规则", not leftovers, ",".join(leftovers))

    for folder, minimum in (("agents", 6), ("commands", 3)):
        files = sorted((cfg / folder).glob("*.md")) if (cfg / folder).is_dir() else []
        names = [p.stem for p in files]
        missing = [p.name for p in files if not _frontmatter(p).get("description")]
        add(f"{folder} 数量", len(files) >= minimum, f"{len(files)} 个：{','.join(names)}")
        add(f"{folder} frontmatter", not missing, ",".join(missing))

    settings = C.read_json(cfg / "settings.json", default={}) or {}
    absent = [key for key in C.REMOVED_SETTINGS if key in settings]
    add_volatile("办公类配置键已移除", not absent, ",".join(absent))

    permissions = settings.get("permissions") or {}
    add("permissions.defaultMode", permissions.get("defaultMode") == "acceptEdits",
        str(permissions.get("defaultMode")))
    add("autoCompactWindow", "autoCompactWindow" not in settings
        or C.valid_compact_window(settings["autoCompactWindow"]),
        str(settings["autoCompactWindow"]) if "autoCompactWindow" in settings else "auto (field absent)")
    snapshot = settings.get("fileCheckpointingEnabled") is True
    memory_on = (settings.get("memory") or {}).get("enabled") is True
    add_volatile("记忆与快照开关", snapshot and memory_on,
                 "" if snapshot and memory_on
                 else f"fileCheckpointingEnabled={settings.get('fileCheckpointingEnabled')} "
                      f"memory.enabled={(settings.get('memory') or {}).get('enabled')}")

    # Registering the right script under the wrong event is silently useless, so
    # check the pairing (event + matcher) rather than just "the filename appears".
    hooks = settings.get("hooks") or {}
    problems: list[str] = []
    seen: list[str] = []
    for script in HOOK_SCRIPTS:
        event = C.HOOK_EVENTS[script]
        expected = set(C.HOOK_MATCHERS.get(script, ()))
        found = False
        for group in hooks.get(event) or []:
            matcher = group.get("matcher") or ""
            patterns = {part.strip() for part in matcher.split("|") if part.strip()}
            for hook in group.get("hooks", []):
                if script not in (hook.get("command") or ""):
                    continue
                found = True
                # An empty matcher matches every tool, which covers the expectation.
                gap = expected - patterns if patterns else set()
                if gap:
                    problems.append(f"{script} matcher 缺 {','.join(sorted(gap))}")
        if found:
            seen.append(f"{event}:{script}")
        else:
            problems.append(f"{script} 未注册到 {event}")
    add("hooks 已注册", not problems, "; ".join(problems) or ",".join(seen))

    hooks_dir = cfg / "hooks"
    for script in HOOK_SCRIPTS:
        path = hooks_dir / script
        add(f"hook 文件 {script}", path.is_file(), "")
    add("hook 上下文依赖", (hooks_dir / "_hooklib.py").is_file(), "_hooklib.py")

    if (hooks_dir / "post_edit_check.py").is_file():
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.py"
            broken.write_text("def f(:\n    pass\n", encoding="utf-8")
            code, output = _run_hook(hooks_dir / "post_edit_check.py",
                                      {"tool_name": "Edit", "tool_input": {"file_path": str(broken)}}, cfg,
                                      stdout=True)
            try:
                feedback = json.loads(output).get("hookSpecificOutput", {})
            except (ValueError, AttributeError):
                feedback = {}
            valid = (feedback.get("hookEventName") == "PostToolUse"
                     and str(broken) in feedback.get("additionalContext", "")
                     and "Syntax check failed" in feedback.get("additionalContext", ""))
            add("hook 坏文件语法反馈", code == 0 and valid, f"exit={code}, context={valid}")
            good = Path(tmp) / "good.py"
            good.write_text("x = 1\n", encoding="utf-8")
            code, _ = _run_hook(hooks_dir / "post_edit_check.py",
                                {"tool_name": "Edit", "tool_input": {"file_path": str(good)}}, cfg)
            add("hook 语法门禁放行好文件", code == 0, f"exit={code}")

    if (hooks_dir / "pre_tool_guard.py").is_file():
        code, message = _run_hook(hooks_dir / "pre_tool_guard.py",
                                  {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}, cfg)
        add("hook 危险命令拦截", code == 2, f"exit={code} {message.strip()[:60]}")
        code, _ = _run_hook(hooks_dir / "pre_tool_guard.py",
                            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, cfg)
        add("hook 普通命令放行", code == 0, f"exit={code}")

    if (hooks_dir / "session_start.py").is_file():
        code, output = _run_hook(hooks_dir / "session_start.py", {"cwd": str(C.REPO)}, cfg, stdout=True)
        try:
            response = json.loads(output).get("hookSpecificOutput", {})
        except (ValueError, AttributeError):
            response = {}
        try:
            probe = subprocess.run(["git", "-C", str(C.REPO), "rev-parse", "--is-inside-work-tree"],
                                   capture_output=True, timeout=5)
            is_repo = probe.returncode == 0 and probe.stdout.strip() == b"true"
        except (OSError, subprocess.SubprocessError):
            is_repo = False
        valid = (response.get("hookEventName") == "SessionStart"
                 and "<repo_state>" in response.get("additionalContext", "")) if is_repo else not output.strip()
        add("hook 会话启动可执行", code == 0 and valid, f"exit={code}, context={valid}")

    state = C.read_json(C.state_dir(cfg) / "state.json", default={}) or {}
    prompt_context = state.get("options", {}).get("prompt_context") is True
    optional = [hook for group in hooks.get("UserPromptSubmit", []) for hook in group.get("hooks", [])
                if install._is_harness_hook(hook.get("command", ""),
                    (str(hooks_dir / "prompt_submit.py").replace("\\", "/"),))]
    add("可选提问 hook", bool(optional) == prompt_context,
        "enabled" if prompt_context else "disabled")
    if prompt_context:
        script = hooks_dir / "prompt_submit.py"
        code, output = _run_hook(script, {"cwd": str(C.REPO), "prompt": "检查当前任务"}, cfg, stdout=True)
        try:
            response = json.loads(output).get("hookSpecificOutput", {})
        except (ValueError, AttributeError):
            response = {}
        add("可选提问上下文", code == 0 and response.get("hookEventName") == "UserPromptSubmit"
            and "<turn_context>" in response.get("additionalContext", ""), f"exit={code}")

    prompt = C.PROFILE / "prompt" / "prompt.tpl"
    targets = install.prompt_targets(cfg)
    same = bool(targets) and all(t.read_bytes() == prompt.read_bytes() for t in targets)
    add("系统提示已替换", same, f"{len(targets)} 个目标")

    plugins = C.read_json(C.PROFILE / "plugins.json", default={}) or {}
    enabled = settings.get("enabledPlugins") or {}
    wrong = [pid for pid in plugins.get("disable", []) if enabled.get(pid) is not False]
    add_volatile("办公插件已停用", not wrong, f"{len(wrong)} 个未停用：{','.join(wrong)}" if wrong else "")
    # The keep list is the other half: an office-profile install that turns the
    # engineering plugins off is just as broken as one that leaves office on.
    kept = [pid for pid in plugins.get("keep", []) if enabled.get(pid) is not True]
    add_volatile("工程插件已启用", not kept, f"{len(kept)} 个未启用：{','.join(kept)}" if kept else "")

    disabled_skills = C.read_json(C.PROFILE / "builtin-skills-off.json")
    overrides = settings.get("skillOverrides") or {}
    missing_skills = [name for name in disabled_skills if overrides.get(name) != "off"]
    add_volatile("内置生态技能开关", not missing_skills, ",".join(missing_skills) or f"{len(disabled_skills)} 个关闭")
    required_controls = C.read_json(C.PROFILE / "tool-control.json")
    controls = settings.get("toolControl") or {}
    valid_control = (isinstance(controls, dict) and type(controls.get("version")) is int
                     and controls.get("version") == 1)
    gaps = [key for key, values in required_controls.items()
            if not isinstance(controls, dict) or not isinstance(controls.get(key), list)
            or any(value not in controls[key] for value in values)]
    add("生态工具控制", valid_control and not gaps, ",".join(gaps))

    for root in state.get("workspaces", []):
        path = W.settings_path(Path(root))
        local = C.read_json(path, default={}) or {}
        enabled_local = local.get("enabledPlugins", {}) if isinstance(local, dict) else {}
        if not isinstance(enabled_local, dict):
            add("工作区插件覆盖", False, f"{path}: enabledPlugins 必须为对象")
            continue
        wrong = [key for key in plugins["disable"] if enabled_local.get(key) is not False]
        wrong += [key for key in plugins["keep"] if enabled_local.get(key) is not True]
        add("工作区插件覆盖", not wrong, f"{path}: {len(wrong)} 项偏离")

    add("hook 解释器可用", C.interpreter_available(), C.interpreter())
    return checks


def _tail(path: Path, size: int = 400_000) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        length = handle.tell()
        handle.seek(max(0, length - size))
        return handle.read().decode("utf-8", "replace")


def _has_profile_system_input(value: object) -> bool:
    """Inspect system-role input only; a tool result quoting our template is not evidence.

    The trace writer truncates long input arrays. Decode complete prefix messages
    individually so a complete system message remains usable in that case.
    """
    messages = value
    if isinstance(value, str):
        try:
            messages = json.loads(value)
        except ValueError:
            messages = []
            source = value.lstrip()
            if not source.startswith("["):
                return False
            position = 1
            decoder = json.JSONDecoder()
            while position < len(source):
                while position < len(source) and source[position] in " \r\n\t,":
                    position += 1
                try:
                    item, position = decoder.raw_decode(source, position)
                except ValueError:
                    break
                messages.append(item)
    if isinstance(messages, dict):
        messages = messages.get("messages", [])
    if not isinstance(messages, list):
        return False
    for item in messages:
        if not isinstance(item, dict) or item.get("role") != "system":
            continue
        content = item.get("content")
        if isinstance(content, str) and MARKER in content:
            return True
        if isinstance(content, list) and any(isinstance(block, dict) and MARKER in str(block.get("text", ""))
                                             for block in content):
            return True
    return False


def _trace_has_profile(path: Path) -> bool:
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue  # A live writer can leave an incomplete final line.
                if not isinstance(record, dict):
                    continue
                span = record.get("span", {})
                if (record.get("type") == "span_end" and isinstance(span, dict)
                        and span.get("type") == "generation"
                        and _has_profile_system_input(span.get("toolInput"))):
                    return True
        return False
    data = C.read_json(path, default={}) or {}
    return any(isinstance(span, dict) and span.get("type") == "generation"
               and _has_profile_system_input(span.get("toolInput")) for span in data.get("spans", []))


def _latest_line(logs: list[Path], pattern: re.Pattern, pid: int | None) -> re.Match | None:
    """Latest matching log line for pid, ordered by the line's own timestamp, not file mtime."""
    best, best_stamp = None, ""
    for log in logs:
        with log.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = pattern.search(line)
                if not match or (pid is not None and int(match.group("pid")) != pid):
                    continue
                stamp = line[:25]
                if stamp >= best_stamp:
                    best, best_stamp = match, stamp
    return best


# Prewarm activation ("args=") or cold start ("[Dispatch] entry opts ... argv=").
LAUNCH = re.compile(r"\[pid=(?P<pid>\d+)\].*(?:\[Prewarm\] activated pid=\d+ .*?args=|\[Dispatch\] entry opts: .*? argv=)(?P<args>\[.*\])\s*$")
MCP_CONNECTED = re.compile(r"\[pid=(?P<pid>\d+)\] \[MCP\]\[buildMcpServers\] connected servers=\[(?P<servers>[^\]]*)\]")


def _launch_args(logs: list[Path], pid: int | None) -> list[str] | None:
    """CLI argv as the engine received it (prewarm activation line)."""
    match = _latest_line(logs, LAUNCH, pid)
    try:
        args = json.loads(match.group("args")) if match else None
    except ValueError:
        return None
    return args if isinstance(args, list) else None


def _arg_value(args: list[str], flag: str) -> str | None:
    """Last occurrence wins, as in the CLI's own option parsing."""
    positions = [i for i, value in enumerate(args) if value == flag and i + 1 < len(args)]
    return args[positions[-1] + 1] if positions else None


def runtime_checks(cfg: Path, pid: int | None = None) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []

    def add(name: str, state: bool | str, detail: str = "") -> None:
        checks.append((name, _state(state), detail))

    hook_log = cfg / "hooks" / "harness-hooks.log"
    entries = hook_log.read_text(encoding="utf-8", errors="replace").splitlines() if hook_log.is_file() else []
    add("hook 运行日志", bool(entries), f"{len(entries)} 行，最后：{entries[-1][:80] if entries else ''}")

    traces = sorted([*cfg.glob("traces/*/trace_*.json"), *cfg.glob("traces/*/trace_*.jsonl")],
                    key=lambda p: p.stat().st_mtime)
    if pid is None and traces and traces[-1].parent.name.isdigit():
        pid = int(traces[-1].parent.name)
    if pid is not None:
        traces = [path for path in traces if path.parent.name == str(pid)]
    scope = f"pid={pid}" if pid is not None else "all traces"

    # Per-workspace session logs are named "<workspace>__<hash>.log".
    logs = sorted((p for p in cfg.glob("logs/**/*__*.log") if p.is_file()), key=lambda p: p.stat().st_mtime)
    if logs:
        loaded = []
        memory_seen = False
        for log in logs:
            memory_block = False
            with log.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.startswith("["):
                        scoped = pid is None or f"[pid={pid}]" in line
                        memory_block = scoped and "[MemoryLoader]" in line
                        if memory_block:
                            loaded.extend(re.findall(r"\[MemoryLoader\]\s+Loaded (\d+) memory rules", line))
                    memory_seen |= memory_block and "CODEBUDDY.md" in line
        add("运行时加载记忆规则", bool(loaded), f"{scope}, Loaded {loaded[-1] if loaded else '?'} 条")
        add("记忆包含 CODEBUDDY.md", memory_seen, scope)
    else:
        add("运行时日志", False, "未找到 harness__*.log")

    hit = ""
    for trace in reversed(traces[-6:]):
        try:
            if _trace_has_profile(trace):
                hit = trace.name
                break
        except OSError:
            continue
    add("系统提示已生效（system 输入）", bool(hit), f"{scope}, {hit or '最近 trace 未见标记'}")

    args = _launch_args(logs, pid)
    if args is None:
        add("引擎实际工具清单", WARN, f"{scope}, 日志中未找到启动参数")
        return checks
    tools = _arg_value(args, "--tools")
    add("引擎实际工具清单", tools == C.CODE_TOOLS,
        f"{scope}, {len(tools.split(',')) if tools else 0} 项" + ("" if tools == C.CODE_TOOLS else f"：{(tools or '')[:120]}"))
    deny = set(C.read_json(C.PROFILE / "tool-control.json")["disabledMcpServerIds"])
    connected = _latest_line(logs, MCP_CONNECTED, pid)
    if connected is None:
        add("生态 MCP 未启动", WARN, f"{scope}, 日志中未找到 MCP 连接记录")
    else:
        servers = {name.strip() for name in connected.group("servers").split(",") if name.strip()}
        leaked = sorted(servers & deny)
        add("生态 MCP 未启动", not leaked, f"{scope}, 已连接：{','.join(sorted(servers)) or '无'}"
            + (f"；仍包含 {','.join(leaked)}" if leaked else ""))
    return checks


def report(checks: list[tuple[str, str, str]]) -> bool:
    width = max(len(name) for name, _, _ in checks) if checks else 10
    for name, state, detail in checks:
        print(f"{LABELS.get(state, 'FAIL')}  {name.ljust(width)}  {detail}")
    failures = [name for name, state, _ in checks if state == FAIL]
    warnings = [name for name, state, _ in checks if state == WARN]
    passed = sum(1 for _, state, _ in checks if state == PASS)
    suffix = f"，{len(warnings)} 项警告" if warnings else ""
    print(f"\n{passed}/{len(checks)} 通过{suffix}")
    return not failures


def main(argv: list[str]) -> int:
    runtime = "--runtime" in argv
    cfg = C.config_dir()
    checks = static_checks(cfg)
    if runtime:
        checks += runtime_checks(cfg)
    return 0 if report(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
