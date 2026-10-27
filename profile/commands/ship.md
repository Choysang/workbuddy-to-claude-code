---
description: 端到端交付：检查 → 提交 → 推送 → 开 PR（推送前必须确认）
argument-hint: "[PR 标题或说明，可留空]"
allowed-tools: Bash, PowerShell, Read, Grep, Glob
---

# /ship

把已完成的工作推到远端并开 PR。$ARGUMENTS

## 步骤

1. 确认真的做完了：跑与改动相关的测试/构建。失败就停，不要推一个红的分支。
2. 确认当前分支不是 `main`/`master`。是的话先建分支，命名沿用仓库习惯（`feat/`、`fix/`、`chore/`）。
3. `/commit` 的流程走一遍，确保工作区干净。
4. **推送前停下来向用户确认**：目标远程、分支名、将要推送的 commit 列表。得到确认后 `git push -u origin <branch>`。
5. 用 `gh pr create` 开 PR：标题一行说清成果；正文包含背景、改动点、验证方式（贴命令与结果）、风险与回滚方式、未覆盖项。
6. 报告 PR 链接与 CI 状态。

## 禁止

- 未经确认 push、`push --force`、直接推 `main`。
- 在 PR 正文里写"已测试"却没有贴出命令与输出。
- 顺手改无关文件来"让 PR 更完整"。

## 返回

分支名 → commit 列表 → PR 链接 → 验证证据 → CI 状态 → 未完成项。
