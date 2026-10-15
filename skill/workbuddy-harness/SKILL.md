---
name: workbuddy-harness
description: WorkBuddy harness 改造与维护。Use when 用户要安装/重打/验证 WorkBuddy 的 Claude Code 风格 harness 改造、WorkBuddy 自动升级后恢复补丁、跑 harness 验收、审计 WorkBuddy 技能臃肿，或问 "workbuddy 升级后怎么恢复 / post-update / verify --runtime / harness 改造"。Triggers: WorkBuddy 升级、补丁失效、harness 重打、toneStyle 重置、weixinpay 复活、技能沉淀清理。
---

# WorkBuddy Harness

统一入口脚本：`<repo>\scripts\harness.py`（内部调用 install / patch_code_prompt / patch_tools / tune / extras / verify / rollback）。

## 场景 → 命令

| 场景 | 命令 |
|---|---|
| 首次安装 | **`python harness.py setup`** 一条命令（预览加 `--dry-run`） |
| **WorkBuddy 自动升级后**（补丁失效、toneStyle 变回 professional、停用插件复活） | 退出 WorkBuddy → `python harness.py post-update` → 手动复查（见下）→ 验收 → `verify --runtime` |
| 只想看补丁状态 | `python harness.py status` |
| 完整校验 | `python harness.py verify`；跑过验收任务后加 `--runtime` |
| 回滚 | `python harness.py rollback [备份目录]`（字节级还原） |
| 技能审计（防自动沉淀泛滥） | `python harness.py skills-audit`（只报告，不删；归档移去 backups/） |

## 硬性前置

1. **先退出 WorkBuddy 再跑任何写命令**——运行中它会把配置写回，且脚本进程保护会拒绝执行。托盘右键退出，不是关窗口。
2. 脚本只动 `~/.workbuddy-ai/` 与插件缓存；**永远不碰** `app.asar`（SHA256 完整性校验 + 签名）。

## 必须人工做的步骤（脚本管不了，详见图文手册）

`<repo>\docs\MANUAL-STEPS.md`（含示意图）：

1. 设置 → 打开「自定义 MCP」总开关。
2. 连接器管理 → 右上「自定义连接器」→ context7 / agentmemory / headroom 各点「信任」。
3. 模型设置 → deepseek-v4.1-flash 的上下文下拉选 1M（一次性）。
4. 设置 → 关「本地技能与记忆沉淀」（防技能自动泛滥）。
5. 发验收任务（speed.py parse_speed），观察：任务清单 → 每步跑测试 → code-reviewer → 汇报。

## 验收判据（verify --runtime 的证据来源）

- hook 日志 `~/.workbuddy-ai/hooks/post_edit_check.log` 有记录。
- trace 请求含精简系统提示（无办公助手内容）与 rules 注入。
- prompt 中位应在 5–6 万 token 量级（改造前 24.8 万）。

## 踩坑速查（历史实测）

- `CODEBUDDY.md` 会被识别但**不注入**——工程协议放 `rules/workbuddy-protocol.md`。
- SOUL.md 启动时可能被云端「自定义指令」还原——准则原文双写进 rules/。
- 会话沙箱拦 `cmd.exe`：MCP 启动命令用 node 直调 npx。
- 沙箱 PATH 无 rtk：hook 改写用绝对路径。
- 新 MCP 不点「信任」= 完全不启动，日志无记录。
- 升级会生成新插件缓存目录 → prompt/tools 补丁必然失效，`~/.workbuddy-ai/` 内文件不受影响。

相关：改造教程 `docs/TUTORIAL.md`；评估报告 `<repo>\HARNESS-EVAL.md`。
