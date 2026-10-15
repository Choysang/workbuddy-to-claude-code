---
name: handoff
description: 跨 Agent 会话接力。用户输入 /handoff（Codex 为 $handoff）时封存当前会话并得到编号；输入 /handoff <编号> 时在任意 Agent 接手继续干。也用于：换会话或换模型前、上下文快满、长任务到里程碑、把工作拆成并行 lane、汇合 lane。
allowed-tools: Bash(handoff *)
---
<!-- handoff:skill -->
# handoff：封存与接手

参数：$ARGUMENTS
（若上一行显示的是字面量 `$ARGUMENTS`，参数就是用户消息里 `$handoff` 之后的文字。）

按参数分流：空 → **封存**；`7`、`myapp-7` → **接手**；`join …` → **汇合**；`take`、`ls`、`show …`、`sync` → 运行 `handoff <参数>` 并把结果转述给用户。

`handoff` 是确定性工具：它从 harness 原始记录里逐字抽取用户原话、从 git 生成账本、做快照和编号，从不调用模型。判断由你来做。

## 封存

1. 运行 `handoff prepare --session ${CLAUDE_SESSION_ID}`。它在 `.handoff/draft/` 里放好草稿：`brief.md`、`state.md`（已带上一个交接的内容），以及只读参考 `_voice.md`（新增原话及编号）、`_ledger.md`（git 账本）。
2. 编辑 `brief.md`，即项目提示词，接手者每次都会读，≤120 行，内容稳定：
   - 目标、范围（做/不做）、最终验收标准（每条是命令或可观察结果）。
   - 用户的持久要求：按主题归并，每条末尾引用原话编号，如 `[v3.2]`。只引用 `_voice.md` 或更早交接里真实存在的编号。
   - 被否决的方案：方案 — 原因 — 谁否决。这一节防止接手者重走死路，宁多勿漏。
   - 架构与约定：冻结的接口、目录所有权、命名与提交约定。
3. 编辑 `state.md`，即动态状态，≤200 行：
   - front matter 的 `next` 写第一步，要做到接手者不读其他内容也能马上动手；`accept` 写这一步怎么算完成。两者每次封存都要重写。
   - 进度：完成 / 进行中 / 未开始，每项带证据（提交、测试、命令输出）。
   - 决定：每条带一个标签。`[user]` 用户拍板，必须引用原话；`[proven]` 由测试或运行证明，写证据；`[agent]` 你的判断，尚未验证；`[open]` 待决问题。
   - 现场：仍在运行的后台任务、远程作业、临时环境。分支、HEAD、未提交改动由工具自动记录，不用写。
   - 只写事实；不确定的写「未验证」。用用户的语言写。
4. 没有原始记录时（prepare 报告新增原话 0 条，而用户在本会话说过话），把用户的关键原话逐字写进 `.handoff/draft/recalled.md`，一段一条。
5. 要并行时：先提交，再参照 `_fork.example.md` 写 `fork.md`，每条 lane 写清 `next`、`accept`、`owns`（只许改的路径），lane 之间的路径不要重叠。
6. 运行 `handoff seal --session ${CLAUDE_SESSION_ID}`。校验不过就按提示修改后重跑。
7. 把 seal 的输出原样给用户，它包含编号和接手方式。

## 接手

1. 运行 `handoff load <参数> --session ${CLAUDE_SESSION_ID}`（跨目录用 `项目-编号`，输出会给出仓库路径，之后在那里工作）。
2. 通读输出。冲突时以高者为准：仓库文件、测试、git > 用户原话 > brief/state > 你的记忆。
3. 现场报告是信息，不是关卡：HEAD 或工作区有差异，就看差异、判断它和下一步的关系，不必问用户。
4. 用三行告诉用户：载入了什么、现场如何、从哪一步开始。然后立即执行第一步。
5. 需要原话全文：`handoff show v7.3`；全部原话：`handoff show 7 voice`；历次账本：`handoff show 7 history`。

## 汇合

1. 运行 `handoff join <分叉点编号或各 lane 末端编号> --session ${CLAUDE_SESSION_ID}`。
2. 按 `.handoff/draft/_lanes.md` 合并各 lane 分支（`git merge lane/…`），解决冲突，跑各 lane 和总体的验收。
3. 写汇合后的 `brief.md`、`state.md`，再 `handoff seal --session ${CLAUDE_SESSION_ID}`。
