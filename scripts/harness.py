#!/usr/bin/env python3
"""WorkBuddy harness control: apply | status | verify | rollback | doctor."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import common as C
import install
import rollback as rollback_mod
import verify


def cmd_apply(args: argparse.Namespace) -> int:
    result = install.apply(dry_run=args.dry_run, prompt_context=args.prompt_context, workspaces=args.workspace)
    if not result["actions"]:
        print("已是最新状态，无需改动。")
        return 0
    verb = "将执行" if args.dry_run else "已执行"
    print(f"{verb} {len(result['actions'])} 项改动：")
    for action in result["actions"]:
        print(f"  - {action}")
    if args.dry_run:
        print("\n这是预览，未写入任何文件。去掉 --dry-run 生效。")
    else:
        print(f"\n备份：{result['state'].get('backup')}")
        print("重启 WorkBuddy 后生效。")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    cfg = C.config_dir()
    state = C.read_json(C.state_dir(cfg) / "state.json", default={})
    print(f"配置目录：{cfg}")
    print(f"已应用：{state.get('applied', '未安装')}  版本：{state.get('version', '-')}")
    print(f"最近备份：{C.latest_backup(cfg) or '无'}")

    drift = install.apply(cfg=cfg, dry_run=True)["actions"]

    if drift:
        print(f"\n{len(drift)} 处与 profile 不一致：")
        for item in drift:
            print(f"  - {item}")
        print("\n运行 `python scripts/harness.py apply` 同步。")
    else:
        print("\n与 profile 完全一致。")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    checks = verify.static_checks(C.config_dir())
    if args.runtime:
        checks += verify.runtime_checks(C.config_dir(), pid=args.pid)
    return 0 if verify.report(checks) else 1


def cmd_build(args: argparse.Namespace) -> int:
    import engineering
    result = engineering.build(app_dir=args.app_dir, output=args.output,
                               shortcuts=not args.no_shortcuts, workspaces=args.workspace)
    print(f"工程版 {'已存在并通过校验' if result['reused'] else '已生成'}：{result['edition']}")
    print(f"原厂版本：{result['version']}。原安装未修改；本版本以后直接使用工程版快捷方式。")
    if args.launch:
        subprocess.Popen([str(Path(result["edition"]) / engineering.EXE)], cwd=result["edition"])
    else:
        print("请退出旧 WorkBuddy 后，从“WorkBuddy AI 工程版”启动。更新原厂版本后重新运行 build。")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    backup = Path(args.backup) if args.backup else None
    result = rollback_mod.rollback(backup=backup, dry_run=args.dry_run)

    if result["dry_run"]:
        print(f"将从 {result['backup']} 回滚 {len(result['changed'])} 项：")
    else:
        print(f"已从 {result['backup']} 回滚 {len(result['changed'])} 项：")
    for path in result["changed"]:
        print(f"  {path}")

    if result["kept"]:
        print(f"\n保留 {len(result['kept'])} 个安装后被改过的文件（不覆盖你的改动）：")
        for path in result["kept"]:
            print(f"  {path}")

    if result["missing"]:
        print(f"\nFAIL {len(result['missing'])} 项在备份里找不到副本，目标保持原样：")
        for path in result["missing"]:
            print(f"  {path}")
        return 1

    if result["dry_run"]:
        print("\n这是预览，未写入任何文件。去掉 --dry-run 生效。")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    cfg = C.config_dir()
    rows = []
    rows.append(("配置目录可写", cfg.is_dir() and _writable(cfg), str(cfg)))
    rows.append(("python 解释器", C.interpreter_available(), C.interpreter()))
    rows.append(("node 可用", bool(shutil.which("node")), shutil.which("node") or "未找到"))
    rows.append(("git 可用", bool(shutil.which("git")), shutil.which("git") or "未找到"))
    rows.append(("提示词目标", bool(install.prompt_targets(cfg)),
                 f"{len(install.prompt_targets(cfg))} 个 welcomemode-code 版本"))
    hooks_dir = cfg / "hooks"
    rows.append(("hooks 目录可写", _writable(hooks_dir) if hooks_dir.is_dir() else False, str(hooks_dir)))
    rows.append(("技能目录", (cfg / "skills").is_dir(), str(cfg / "skills")))
    rows.append(("仓库 profile", C.PROFILE.is_dir(), str(C.PROFILE)))

    for name, ok, detail in rows:
        print(f"{'OK  ' if ok else 'FAIL'}  {name:<16} {detail}")
    return 0 if all(ok for _, ok, _ in rows) else 1


def _writable(path: Path) -> bool:
    probe = path / ".harness-write-probe"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    apply_parser = sub.add_parser("apply", help="安装或同步 profile 到本机配置目录")
    apply_parser.add_argument("--dry-run", action="store_true", help="只显示计划，不写文件")
    optional = apply_parser.add_mutually_exclusive_group()
    optional.add_argument("--prompt-context", dest="prompt_context", action="store_true",
                          help="启用每次提问的时间与工作区提示 hook")
    optional.add_argument("--no-prompt-context", dest="prompt_context", action="store_false",
                          help="关闭可选提问 hook，保留三个默认 hooks")
    apply_parser.set_defaults(prompt_context=None)
    apply_parser.add_argument("--workspace", type=Path, action="append",
                              help="为此工作区写入重启后仍有效的插件覆盖；可重复传入")
    apply_parser.set_defaults(func=cmd_apply)

    sub.add_parser("status", help="显示 profile 与已安装状态的差异").set_defaults(func=cmd_status)

    build_parser = sub.add_parser("build", help="更新后运行一次：生成持久独立工程版并同步配置")
    build_parser.add_argument("--app-dir", type=Path, help="原厂 WorkBuddy 安装目录；首次指定后记住")
    build_parser.add_argument("--output", type=Path, help="独立版本输出目录")
    build_parser.add_argument("--no-shortcuts", action="store_true", help="不更新工程版快捷方式")
    build_parser.add_argument("--launch", action="store_true", help="生成后启动；请先退出旧实例")
    build_parser.add_argument("--workspace", type=Path, action="append", help="同时应用的工作区；可重复")
    build_parser.set_defaults(func=cmd_build)

    verify_parser = sub.add_parser("verify", help="静态校验，--runtime 追加运行时证据")
    verify_parser.add_argument("--runtime", action="store_true", help="检查日志、trace 与 hook 记录")
    verify_parser.add_argument("--pid", type=int, help="限定某次真实 CLI 进程的日志与 trace（与 --runtime 一起使用）")
    verify_parser.set_defaults(func=cmd_verify)

    rollback_parser = sub.add_parser("rollback", help="从备份恢复配置")
    rollback_parser.add_argument("--backup", help="指定备份目录，默认最近一次")
    rollback_parser.add_argument("--dry-run", action="store_true")
    rollback_parser.set_defaults(func=cmd_rollback)

    sub.add_parser("doctor", help="检查环境依赖").set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
